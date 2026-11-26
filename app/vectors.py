"""Safe, editable SVG objects; raster conversion traces black/white contours."""
import copy
import hashlib
import json
import math
import re
import base64
import xml.etree.ElementTree as ET
from PIL import Image
from . import images
from .core import uid

TAGS={'g','path','line','polyline','polygon','rect','circle','ellipse','defs','marker','title','desc','linearGradient','radialGradient','stop'}
GRADIENT={'linearGradient','radialGradient','stop'}      # 앱 도식의 음영. defs 안에서만 쓴다.
ATTRS=set('id data-element transform d points x y x1 y1 x2 y2 width height rx ry cx cy r fill fill-rule fill-opacity stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity opacity marker-start marker-mid marker-end markerWidth markerHeight markerUnits refX refY orient viewBox preserveAspectRatio vector-effect offset stop-color stop-opacity fx fy gradientUnits'.split())

def safe_fragment(source, defs=False):
    if not isinstance(source,str) or len(source)>900000 or '<!' in source: raise ValueError('그림 객체 SVG 형식 오류')
    root=ET.fromstring('<svg>'+source+'</svg>')
    if len(list(root.iter()))>5000: raise ValueError('그림 객체가 너무 복잡합니다.')
    for node in list(root.iter())[1:]:
        tag=node.tag.split('}')[-1]
        if tag not in TAGS or (not defs and (tag in ('defs','marker') or tag in GRADIENT)): raise ValueError('그림 객체에는 선·도형만 넣을 수 있습니다. 글씨는 글씨 레이어를 사용하세요.')
        node.tag=tag
        for key,val in node.attrib.items():
            if key not in ATTRS or len(val)>800000: raise ValueError('지원하지 않는 SVG 속성: '+key)
            if re.search(r'url\(',val,re.I) and not re.fullmatch(r'url\(#[\w-]+\)',val): raise ValueError('외부 SVG 참조는 허용되지 않습니다.')
            if any(s in val.lower() for s in ('javascript:','data:','http:','https:')): raise ValueError('외부 SVG 참조 오류')
        if tag not in ('title','desc') and node.text and node.text.strip(): raise ValueError('그림 객체에 글씨를 넣을 수 없습니다.')
    return ''.join(ET.tostring(n,encoding='unicode') for n in root)

# 창작 요소 PNG(2026-11-26): svg 대신 같은 회차 assets의 PNG 파일 이름과 그 그림의 기본 크기를 가진다.
RASTER_NAME=re.compile(r'[a-f0-9]{16}\.png')

def raster_object(item):
    name=str(item.get('raster') or '')
    if not RASTER_NAME.fullmatch(name): raise ValueError('그림 요소 PNG 파일 이름 오류')
    size=[item.get('width'),item.get('height')]
    if any(type(n) not in (int,float) or not math.isfinite(n) or not 0<n<=4000 for n in size): raise ValueError('그림 요소 PNG 크기 오류')
    if str(item.get('svg') or ''): raise ValueError('PNG 그림 요소에는 SVG 도형을 함께 넣을 수 없습니다.')
    return name,size

def normalize_scene(scene):
    if scene is None:return None
    if not isinstance(scene,dict) or scene.get('version')!=1 or not re.fullmatch('[a-f0-9]{64}',str(scene.get('source_sha'))): raise ValueError('그림 객체 버전·원본 정보 오류')
    items=scene.get('objects')
    if not isinstance(items,list) or len(items)>500: raise ValueError('그림 객체는 최대 500개입니다.')
    result=dict(version=1,source_sha=scene['source_sha'],defs=safe_fragment(scene.get('defs',''),True),objects=[])
    for item in items:
        if not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{16}',str(item.get('id'))): raise ValueError('그림 객체 ID 오류')
        matrix=item.get('matrix')
        if not isinstance(matrix,list) or len(matrix)!=6 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>100000 for n in matrix): raise ValueError('그림 객체 위치·크기 오류')
        if abs(matrix[0]*matrix[3]-matrix[1]*matrix[2])<1e-8: raise ValueError('그림 객체의 크기는 0일 수 없습니다.')
        base=dict(id=item['id'],name=str(item.get('name','도형'))[:80],matrix=matrix,visible=item.get('visible',True) is not False,locked=item.get('locked',False) is True)
        if item.get('raster') is not None:
            name,(w,h)=raster_object(item)
            result['objects'].append(dict(base,svg='',raster=name,width=w,height=h))
        else: result['objects'].append(dict(base,svg=safe_fragment(item.get('svg',''))))
    if len({o['id'] for o in result['objects']})!=len(items): raise ValueError('그림 객체 ID 중복')
    if len(json.dumps(result))>2000000: raise ValueError('그림 객체 데이터가 너무 큽니다.')
    return result

def object_from(svg,name):
    return dict(id=uid(),name=name,svg=svg,matrix=[1,0,0,1,0,0],visible=True,locked=False)

def from_svg(source,source_sha,placeholders=None):
    """placeholders: data-element ID → PNG 요소 객체. 그 ID의 자리 상자(rect)를 지우고 그 자리에 PNG 요소를 둔다.
    여러 ID가 같은 객체를 가리키면(한 장 PNG) 처음 나온 자리에 한 번만 둔다."""
    placeholders=placeholders or {}; placed=set()
    images.validate_svg(source)
    root=ET.fromstring(source)
    if root.get('viewBox')!='0 0 1000 640': raise ValueError('객체 변환은 1000 × 640 SVG를 사용합니다.')
    for node in root.iter(): node.tag=node.tag.split('}')[-1]
    defs=[ET.tostring(n,encoding='unicode') for n in root.iter('defs')]
    objects=[]
    def visit(node,ancestors):
        if node.tag in ('defs','title','desc'):return
        element=(node.get('data-element') or '').lower()
        if element in placeholders:
            obj=placeholders[element]
            if id(obj) not in placed: placed.add(id(obj)); objects.append(copy.deepcopy(obj))
            return
        # Group opacity is composited as a whole. Splitting its children changes overlaps.
        if node.tag in ('g','svg') and not (node.tag=='g' and node.get('opacity','1')!='1'):
            attrs={k:v for k,v in node.attrib.items() if k not in ('id','viewBox','width','height','xmlns','version')}
            for child in node:visit(child,ancestors+[attrs])
            return
        if node.tag in ('text','tspan'): raise ValueError('글씨가 포함된 그림입니다. 글씨 없는 배경을 사용하세요.')
        # The canvas already supplies white. Do not make it a selectable giant object.
        if node.tag=='rect' and node.get('fill') in ('white','#fff','#ffffff') and node.get('width')=='1000' and node.get('height')=='640' and not node.get('stroke'):return
        wrapped=copy.deepcopy(node)
        name=node.get('data-element') or node.get('id') or {'path':'경로','line':'선','rect':'사각형','ellipse':'타원','circle':'원','polygon':'다각형','polyline':'꺾은선'}.get(node.tag,'도형')
        for attrs in reversed(ancestors):
            if attrs:
                parent=ET.Element('g',attrs);parent.append(wrapped);wrapped=parent
        objects.append(object_from(ET.tostring(wrapped,encoding='unicode'),name+' '+str(len(objects)+1)))
    visit(root,[])
    for obj in placeholders.values():          # 자리 상자를 못 찾은 요소도 빠뜨리지 않는다
        if id(obj) not in placed: placed.add(id(obj)); objects.append(copy.deepcopy(obj))
    return normalize_scene(dict(version=1,source_sha=source_sha,defs=''.join(defs),objects=objects))

def from_raster(path,source_sha,threshold=190):
    """Trace connected ink regions with directed pixel boundaries (including holes).

    This is deliberately contour extraction, not inferred semantic CAD geometry.
    Collinear boundary points are removed without moving the contour.
    """
    if type(threshold) is not int or not 40<=threshold<=245:raise ValueError('윤곽선 기준은 40~245입니다.')
    with Image.open(path) as img: gray=img.convert('L').resize((1000,640),Image.Resampling.LANCZOS)
    data=gray.tobytes(); ink={i for i,v in enumerate(data) if v<threshold}; objects=[]
    while ink:
        seed=ink.pop(); stack=[seed]; region={seed}
        while stack:
            p=stack.pop();x=p%1000
            for q in (p-1000,p+1000,p-1 if x else -1,p+1 if x<999 else -1):
                if q in ink:ink.remove(q);region.add(q);stack.append(q)
        if len(region)<3:continue
        edges={}
        def add(a,b):edges.setdefault(a,[]).append(b)
        for p in region:
            x,y=p%1000,p//1000
            if p-1000 not in region:add((x,y),(x+1,y))
            if x==999 or p+1 not in region:add((x+1,y),(x+1,y+1))
            if p+1000 not in region:add((x+1,y+1),(x,y+1))
            if x==0 or p-1 not in region:add((x,y+1),(x,y))
        paths=[]
        while edges:
            start=next(iter(edges));point=start;points=[start]
            while True:
                ends=edges[point];nxt=ends.pop()
                if not ends:del edges[point]
                point=nxt
                if point==start:break
                if len(points)>1 and (points[-1][0]-points[-2][0])*(point[1]-points[-1][1])==(points[-1][1]-points[-2][1])*(point[0]-points[-1][0]):points[-1]=point
                else:points.append(point)
            paths.append('M'+' L'.join(f'{x} {y}' for x,y in points)+' Z')
        objects.append(object_from('<path fill="black" fill-rule="evenodd" d="'+' '.join(paths)+'"/>','윤곽 '+str(len(objects)+1)))
        if len(objects)>500:raise ValueError('윤곽선이 500개를 넘습니다. 단순한 흑백 그림을 사용하거나 기준값을 낮춰 주세요.')
    if not objects:raise ValueError('검출된 윤곽선이 없습니다. 기준값을 높여 주세요.')
    return normalize_scene(dict(version=1,source_sha=source_sha,defs='',objects=objects))

def to_svg(scene,read_raster=None):
    """read_raster(name) → PNG 바이트. PNG 요소는 SVG 안에 data URI로 넣어 한 번에 그린다."""
    scene=normalize_scene(scene)
    root=ET.Element('svg',xmlns='http://www.w3.org/2000/svg',viewBox='0 0 1000 640',width='1000',height='640')
    ET.SubElement(root,'rect',width='1000',height='640',fill='white')
    for n in ET.fromstring('<svg>'+scene['defs']+'</svg>'):root.append(n)
    for obj in scene['objects']:
        if not obj['visible']:continue
        group=ET.SubElement(root,'g',transform='matrix('+ ' '.join(str(v) for v in obj['matrix'])+')')
        if obj.get('raster'):
            if read_raster is None: raise ValueError('PNG 그림 요소를 읽을 수 없습니다.')
            data='data:image/png;base64,'+base64.b64encode(read_raster(obj['raster'])).decode()
            ET.SubElement(group,'image',width=str(obj['width']),height=str(obj['height']),preserveAspectRatio='none',href=data)
            continue
        for n in ET.fromstring('<svg>'+obj['svg']+'</svg>'):group.append(n)
    result=ET.tostring(root,encoding='unicode');images.validate_svg(result,allow_raster=True)
    return result

def has_raster(scene):
    return bool(scene) and any(o.get('raster') for o in scene.get('objects',[]))

def digest(scene):
    return hashlib.sha256(json.dumps(scene,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

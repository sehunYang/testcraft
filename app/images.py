"""Validated SVG rendering and HWPML picture embedding, adapted from the image project."""
import base64
import copy
import hashlib
import io
import math
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image
from .core import ROOT
from . import runtime

ALLOWED={'svg','g','path','line','polyline','polygon','rect','circle','ellipse','text','tspan','defs','marker','title','desc','radialGradient','linearGradient','stop'}

def validate_mode_layers(svg,mode,card=None):
    validate_svg(svg)
    root=ET.fromstring(svg)
    groups={node.get('id') for node in root.iter() if node.tag.split('}')[-1]=='g'}
    if any(node.tag.split('}')[-1] in ('text','tspan') for node in root.iter()): raise ValueError('그림에는 글씨·기호를 포함할 수 없습니다. 글씨 레이어로 분리하세요.')
    if root.get('viewBox')!='0 0 1000 640': raise ValueError('글씨 레이어 정합을 위해 그림 viewBox는 0 0 1000 640이어야 합니다.')
    required={'geometry'} if mode=='strict' else {'illustration'} if mode=='flexible' else {'geometry','illustration'}
    if not required.issubset(groups): raise ValueError('SVG 고정·창작 레이어가 누락되었습니다: '+', '.join(sorted(required-groups)))
    if mode=='strict' and 'illustration' in groups: raise ValueError('strict에는 창작 레이어를 사용할 수 없습니다.')
    if mode=='flexible' and 'geometry' in groups: raise ValueError('flexible에는 고정 레이어를 사용할 수 없습니다.')
    def check_parent(node,layer=None):
        layer=node.get('id') if node.get('id') in required else layer
        tag=node.tag.split('}')[-1]
        if tag in ('path','line','polyline','polygon','rect','circle','ellipse') and not layer:
            background=tag=='rect' and node.get('fill') in ('white','#fff','#ffffff') and node.get('width')=='1000' and node.get('height')=='640'
            if not background: raise ValueError('모든 그림 요소를 지정한 고정·창작 레이어 안에 배치하세요.')
        if tag not in ('defs','marker'):
            for child in node: check_parent(child,layer)
    check_parent(root)
    if mode=='mixed' and card:
        from .core import element_ids
        found={}
        for layer,key in [('geometry','image_locked'),('illustration','image_creative')]:
            nodes=[n for n in root.iter() if n.get('id')==layer]
            if len(nodes)!=1: raise ValueError('그림 레이어는 종류별로 한 개여야 합니다.')
            found[layer]={n.get('data-element','').lower() for n in nodes[0].iter() if n.get('data-element')}
            if found[layer]!=element_ids(card[key]): raise ValueError('SVG의 요소 배정이 프롬프트와 다릅니다: '+layer)
        if found['geometry'] & found['illustration']: raise ValueError('고정·창작 레이어가 같은 요소를 포함합니다.')

def validate_svg(svg):
    if len(svg)>1_000_000 or '<!DOCTYPE' in svg.upper() or '<!ENTITY' in svg.upper():
        raise ValueError('SVG 크기 또는 선언 오류')
    root=ET.fromstring(svg)
    if root.tag.split('}')[-1]!='svg': raise ValueError('SVG 루트가 필요합니다.')
    box=root.get('viewBox','').split()
    if len(box)!=4 or any(not re.fullmatch(r'-?\d+(\.\d+)?',v) for v in box): raise ValueError('SVG viewBox가 필요합니다.')
    if not (0<float(box[2])<=4000 and 0<float(box[3])<=4000): raise ValueError('SVG 캔버스 크기 오류')
    if len(list(root.iter()))>5000: raise ValueError('SVG 요소가 너무 많습니다.')
    for node in root.iter():
        if node.tag.split('}')[-1] not in ALLOWED: raise ValueError('허용되지 않는 SVG 요소: '+node.tag)
        for k,v in node.attrib.items():
            key=k.split('}')[-1].lower()
            if key.startswith('on') or key in ('href','style','src') or re.search(r'javascript:|https?:|data:|file:',v,re.I): raise ValueError('외부 참조나 실행 코드가 포함된 SVG입니다.')
            for target in re.findall(r'url\((.*?)\)',v,re.I):
                if not re.fullmatch(r'#[A-Za-z0-9_-]+',target): raise ValueError('외부 SVG 참조는 허용하지 않습니다.')
    return svg

def render_svg(svg, path):
    validate_svg(svg)
    path.with_suffix('.svg').write_text(svg,encoding='utf-8')
    node=runtime.node_executable(ROOT)
    if not node: raise ValueError('SVG 렌더링에 Node.js가 필요합니다.')
    env=runtime.node_environment(ROOT)
    proc=subprocess.run([node,str(ROOT/'app/render.cjs'),str(path.with_suffix('.svg')),str(path)],capture_output=True,encoding='utf-8',env=env,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if proc.returncode: raise ValueError('SVG 렌더링 실패: '+proc.stderr[-1000:])

def normalize_png(raw):
    Image.MAX_IMAGE_PIXELS=20_000_000
    with Image.open(io.BytesIO(raw)) as img:
        if img.width*img.height>20_000_000: raise ValueError('이미지는 2천만 픽셀 이하여야 합니다.')
        img.load()
        canvas=Image.new('RGB',img.size,'white')
        if img.mode=='RGBA': canvas.paste(img,mask=img.getchannel('A'))
        else: canvas.paste(img.convert('RGB'))
        out=io.BytesIO(); canvas.save(out,format='PNG'); return out.getvalue()

def trim_margins(png, pad=.03):
    """그림 둘레의 빈 여백을 잘라 낸다. 기출 그림처럼 내용만큼만 차지하게. (잘린 PNG, 원래 크기)"""
    with Image.open(io.BytesIO(png)) as img:
        size=img.size; gray=img.convert('L')
        box=gray.point(lambda v:255 if v<245 else 0).getbbox()
        if not box: return png,size
        m=round(pad*size[0])
        box=(max(0,box[0]-m),max(0,box[1]-m),min(size[0],box[2]+m),min(size[1],box[3]+m))
        if box[2]-box[0]>=size[0]*.97 and box[3]-box[1]>=size[1]*.97: return png,size
        out=io.BytesIO(); img.convert('RGB').crop(box).save(out,format='PNG')
        return out.getvalue(),size

SIDE_TEXT = 1.7      # 나란히 놓으면 그림 폭이 반쯤으로 줄어 글씨도 작아진다. 그만큼 글씨를 키워 다시 붙인다(2026-11-13).


def relabeled(base_path, objects, k=SIDE_TEXT):
    """글씨 없는 바탕 그림에 글씨를 k배로 키워(각 글씨의 가운데는 그대로) 다시 붙인 PNG. 캔버스 밖으로 나가면 안으로 들인다."""
    from . import labels
    out_objs = []
    for o in labels.normalize_labels(objects):
        if o.get('visible', True) is False: continue
        a = labels.render(o['kind'], o['text'], o['size']); size = max(8, min(120, round(o['size'] * k)))
        b = labels.render(o['kind'], o['text'], size)
        cx, cy = o['x'] + a['width'] / 2, o['y'] + a['height'] / 2
        x = min(max(1, cx - b['width'] / 2), 999 - b['width']); y = min(max(1, cy - b['height'] / 2), 639 - b['height'])
        out_objs.append({**o, 'size': size, 'x': math.floor(x * 10) / 10, 'y': math.floor(y * 10) / 10})
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix='.png'); os.close(fd)
    try:
        labels.compose(base_path, out_objs, tmp)
        return Path(tmp).read_bytes()
    finally:
        os.remove(tmp)


def untouched(block):
    """앱 도식을 교사가 손대지 않았는가: 그림 객체 편집이 없고 글씨가 명세로 그린 그대로인가(2026-11-13).
    손댔으면 반 폭으로 다시 그리지 않는다(다시 그리면 옮기거나 고친 글씨가 사라진다)."""
    from . import diagrams, labels as lab
    if block.get('image_scene') is not None: return False
    try: fresh = diagrams.render(str(block.get('image_locked') or '').strip())[1]
    except Exception: return False
    key = lambda o: (o['kind'], o['text'], round(float(o['x']), 1), round(float(o['y']), 1), o['size'], o.get('rotation', 0), o.get('visible', True) is not False)
    norm = lambda items: sorted(key(o) for o in lab.normalize_labels([dict(o, id=f'{k:016x}') for k, o in enumerate(items)]))
    return norm(fresh) == norm(block.get('image_labels') or [])


def half_width(block, base_path, n):
    """(가)(나) 묶음의 그림 하나를 1/n 폭으로 만든 PNG(글씨는 보통 크기로 보이게).
    앱 도식은 1/n 폭 칸에 처음부터 다시 그리고, AI 그림·지도는 글씨를 n배로 키워 붙인 뒤 그림을 1/n로 줄인다."""
    from . import diagrams, labels as lab
    locked = str(block.get('image_locked') or '').strip()
    if locked.startswith('도식:') and untouched(block):
        try:
            box = (0, 0, round(1000 / n), 640)
            svg, objs = diagrams.render(locked, box)
            import tempfile, os
            d = Path(tempfile.mkdtemp()); base = d / 'base.png'; out = d / 'out.png'
            render_svg(svg, base)
            objs = [{**o, 'id': f'{k:016x}'} for k, o in enumerate(objs)]
            lab.compose(base, objs, out)
            with Image.open(out) as im: png = im.crop((0, 0, box[2] * 3, 1920))
            buf = io.BytesIO(); png.save(buf, format='PNG')
            return buf.getvalue()
        except Exception:
            pass           # 칸에 다시 그리지 못하는 도식은 아래처럼 글씨를 키워 줄인다
    raw = relabeled(base_path, block.get('image_labels') or [], n)
    with Image.open(io.BytesIO(raw)) as im: small = im.convert('RGB').resize((im.width // n, im.height // n), Image.Resampling.LANCZOS)
    buf = io.BytesIO(); small.save(buf, format='PNG')
    return buf.getvalue()


def side_by_side(pngs, captions, gap=90, caption_size=34):
    """(가)(나) 그림을 좌우로 나란히 놓고 아래 가운데에 (가), (나)를 쓴 한 그림(PNG). 글씨는 그림 글씨와 같은 신명 중명조.
    각 그림은 여백을 잘라 낸 원래 배율 그대로 둔다(글씨 크기가 서로 같게)."""
    from . import labels
    figs = [Image.open(io.BytesIO(trim_margins(p)[0])).convert('RGB') for p in pngs]
    caps = []
    for text in captions:
        info = labels.render('korean', text, caption_size)
        caps.append(Image.open(labels.CACHE / (info['key'] + '.png')).convert('RGBA'))
    row_h = max(f.height for f in figs); cap_h = max(c.height for c in caps)
    width = sum(f.width for f in figs) + gap * (len(figs) - 1)
    canvas = Image.new('RGB', (width, row_h + 40 + cap_h), 'white')
    x = 0
    for f, c in zip(figs, caps):
        canvas.paste(f, (x, (row_h - f.height) // 2))
        canvas.paste(c, (x + (f.width - c.width) // 2, row_h + 40), c)
        x += f.width + gap
    out = io.BytesIO(); canvas.save(out, format='PNG')
    return out.getvalue()

def picture(png, bin_id, idx, original=None):
    # Clone the proven Hancom picture structure, preserving schema attributes.
    template=ET.parse(ROOT/'app/picture.xml').getroot()
    width,height=Image.open(io.BytesIO(png)).size
    ow,oh=width*75,height*75
    # 양식 안내: 그림은 크게, 가운데. 2단 한 단의 폭(31041) 안에서 키운다.
    # 여백을 잘라 낸 그림은 원래 그림과 같은 배율로 넣는다(내용 크기는 그대로, 빈 곳만 줄어든다).
    W0,H0=original or (width,height)
    full=min(29000,round(40000*W0/H0))
    dw=round(full*width/W0); dh=round(dw*height/width)
    p=copy.deepcopy(template)
    p.set('ParaShape','20')
    p.find('TEXT').set('CharShape','26')
    so=p.find('.//SHAPEOBJECT'); so.set('InstId',str(2000000000+idx)); so.set('ZOrder',str(300+idx))
    so.find('SIZE').set('Width',str(dw)); so.find('SIZE').set('Height',str(dh))
    so.find('SHAPECOMMENT').text=f'문항 자료 그림 {idx}'
    sc=p.find('.//SHAPECOMPONENT')
    sc.attrib.update(CurHeight=str(dh),CurWidth=str(dw),InstID=str(2100000000+idx),OriHeight=str(oh),OriWidth=str(ow))
    sc.find('ROTATIONINFO').attrib.update(CenterX=str(dw//2),CenterY=str(dh//2))
    scales=sc.findall('RENDERINGINFO/SCAMATRIX')
    for s in scales: s.set('E1','1'); s.set('E5','1')
    scales[-1].set('E1',str(dw/ow)); scales[-1].set('E5',str(dh/oh))
    p.find('.//IMAGERECT').attrib.update(X0='0',X1=str(ow),X2=str(ow),X3='0',Y0='0',Y1='0',Y2=str(oh),Y3=str(oh))
    p.find('.//IMAGECLIP').attrib.update(Bottom=str(oh),Left='0',Right=str(ow),Top='0')
    p.find('.//IMAGEDIM').attrib.update(Height=str(oh),Width=str(ow))
    p.find('.//IMAGE').set('BinItem',str(bin_id))
    return p

def embed(hml, assets, student=False):
    root=ET.fromstring(hml)
    section=root.find('BODY/SECTION')
    before_eq=len(list(section.iter('EQUATION')))
    before_tables=[ET.tostring(t) for t in section.iter('TABLE')]
    mapping=root.find('HEAD/MAPPINGTABLE')
    existing=mapping.find('BINDATALIST')
    if existing is not None and len(existing): raise ValueError('기존 그림이 있는 HML을 덮어쓰지 않습니다.')
    if existing is not None: mapping.remove(existing)
    bins=ET.Element('BINDATALIST',Count=str(len(assets)))
    if assets: mapping.insert(0,bins)
    tail=root.find('TAIL'); storage=ET.SubElement(tail,'BINDATASTORAGE') if assets else None
    # The figure-prompt paragraphs may hold equations ($3 h$ labels) or tables; they leave with the prompt.
    removed_eq=0; removed_tables=[]; trimmed=[]
    for idx,asset in enumerate(assets,1):
        if len(asset)==2: no,png=asset; material_id=None
        else: no,material_id,png=asset
        ps=list(section)
        start_marker=f'〔그림 프롬프트 시작 · {no}번〕' if material_id is None else f'〔그림 프롬프트 시작 · {no}번 · {material_id}〕'
        end_marker=f'〔그림 프롬프트 끝 · {no}번〕' if material_id is None else f'〔그림 프롬프트 끝 · {no}번 · {material_id}〕'
        starts=[i for i,p in enumerate(ps) if start_marker in ''.join(p.itertext())]
        ends=[i for i,p in enumerate(ps) if end_marker in ''.join(p.itertext())]
        if len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]: raise ValueError(f'{no}번 그림 영역 오류')
        for p in ps[starts[0]:ends[0]+1]:
            removed_eq+=len(list(p.iter('EQUATION')))
            removed_tables+=[ET.tostring(t) for t in p.iter('TABLE')]
            section.remove(p)
        png,original=trim_margins(png); trimmed.append(png)
        section.insert(starts[0],picture(png,idx,idx,original))
        ET.SubElement(bins,'BINITEM',BinData=str(idx),Format='PNG',Type='Embedding')
        ET.SubElement(storage,'BINDATA',Encoding='Base64',Id=str(idx),Size=str(len(png))).text=base64.b64encode(png).decode()
    kept_tables=list(before_tables)
    for t in removed_tables: kept_tables.remove(t)
    if before_eq-removed_eq!=len(list(section.iter('EQUATION'))) or kept_tables!=[ET.tostring(t) for t in section.iter('TABLE')]: raise ValueError('그림 삽입 중 수식 또는 표 구조 변경 감지')
    if student:
        for ch in root.iter('CHAR'):
            if any(n.tag in ('MARKPENBEGIN','MARKPENEND') for n in ch):
                text=''.join(ch.itertext()); ch.clear(); ch.text=text
    result=ET.tostring(root,encoding='unicode')
    if '〔그림 프롬프트 시작' in result: raise ValueError('미삽입 그림이 남아 있습니다.')
    for idx,raw in enumerate(trimmed,1):
        if base64.b64decode(root.find(f"TAIL/BINDATASTORAGE/BINDATA[@Id='{idx}']").text)!=raw: raise ValueError('그림 바이트 검증 실패')
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'+result


def diagram_preview(locked):
    """그래프 수치 입력 칸의 미리보기(2026-11-13): 명세를 앱 도식으로 그려 글씨까지 붙인 작은 PNG.
    오류가 있으면 그림 없이 오류만 돌려준다. 교사가 옮긴 글씨는 반영하지 않는 명세 기본 모양이다."""
    from . import diagrams, labels
    if len(str(locked or '')) > 200000: return {'errors': ['도식 명세가 너무 깁니다.']}
    problems = diagrams.errors(locked)
    if problems: return {'errors': problems}
    import tempfile
    try:
        svg, objs = diagrams.render(locked)
    except ValueError as e:
        return {'errors': [str(e)]}
    objs = labels.normalize_labels([dict(o, id=f'{k:016x}') for k, o in enumerate(objs)])
    with tempfile.TemporaryDirectory() as folder:
        base, out = Path(folder) / 'base.png', Path(folder) / 'out.png'
        render_svg(svg, base)
        labels.compose(base, objs, out)
        with Image.open(out) as im:
            small = im.convert('RGB').resize((1000, 640), Image.Resampling.LANCZOS)
        buf = io.BytesIO(); small.save(buf, format='PNG')
    return {'errors': [], 'png': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}

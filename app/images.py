"""Validated SVG rendering and HWPML picture embedding, adapted from the image project."""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image
from .core import ROOT
from . import runtime

ALLOWED={'svg','g','path','line','polyline','polygon','rect','circle','ellipse','text','tspan','defs','marker','title','desc'}

def validate_mode_layers(svg,mode,card=None):
    validate_svg(svg)
    root=ET.fromstring(svg)
    groups={node.get('id') for node in root.iter() if node.tag.split('}')[-1]=='g'}
    if any(node.tag.split('}')[-1] in ('text','tspan') for node in root.iter()): raise ValueError('그림에는 글씨·물리량을 포함할 수 없습니다. 글씨 레이어로 분리하세요.')
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

def picture(png, bin_id, idx):
    # Clone the proven Hancom picture structure, preserving schema attributes.
    template=ET.parse(ROOT/'app/picture.xml').getroot()
    width,height=Image.open(io.BytesIO(png)).size
    ow,oh=width*75,height*75
    dw=min(25000,round(31000*width/height)); dh=round(dw*height/width)
    p=copy.deepcopy(template)
    p.set('ParaShape','1')
    p.find('TEXT').set('CharShape','1')
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
    for idx,asset in enumerate(assets,1):
        if len(asset)==2: no,png=asset; material_id=None
        else: no,material_id,png=asset
        ps=list(section)
        start_marker=f'〔그림 프롬프트 시작 · {no}번〕' if material_id is None else f'〔그림 프롬프트 시작 · {no}번 · {material_id}〕'
        end_marker=f'〔그림 프롬프트 끝 · {no}번〕' if material_id is None else f'〔그림 프롬프트 끝 · {no}번 · {material_id}〕'
        starts=[i for i,p in enumerate(ps) if start_marker in ''.join(p.itertext())]
        ends=[i for i,p in enumerate(ps) if end_marker in ''.join(p.itertext())]
        if len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]: raise ValueError(f'{no}번 그림 영역 오류')
        for p in ps[starts[0]:ends[0]+1]: section.remove(p)
        section.insert(starts[0],picture(png,idx,idx))
        ET.SubElement(bins,'BINITEM',BinData=str(idx),Format='PNG',Type='Embedding')
        ET.SubElement(storage,'BINDATA',Encoding='Base64',Id=str(idx),Size=str(len(png))).text=base64.b64encode(png).decode()
    if before_eq!=len(list(section.iter('EQUATION'))) or before_tables!=[ET.tostring(t) for t in section.iter('TABLE')]: raise ValueError('그림 삽입 중 수식 또는 표 구조 변경 감지')
    if student:
        for ch in root.iter('CHAR'):
            if any(n.tag in ('MARKPENBEGIN','MARKPENEND') for n in ch):
                text=''.join(ch.itertext()); ch.clear(); ch.text=text
    result=ET.tostring(root,encoding='unicode')
    if '〔그림 프롬프트 시작' in result: raise ValueError('미삽입 그림이 남아 있습니다.')
    for idx,asset in enumerate(assets,1):
        raw=asset[-1]
        if base64.b64decode(root.find(f"TAIL/BINDATASTORAGE/BINDATA[@Id='{idx}']").text)!=raw: raise ValueError('그림 바이트 검증 실패')
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'+result

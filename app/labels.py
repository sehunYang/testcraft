"""Editable text objects. Exact font rendering is shared by preview and export."""
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from PIL import Image
from .core import ROOT
from . import runtime

FONT=ROOT/'app/fonts/latinmodern-math-1959/otf/latinmodern-math.otf'
CACHE=runtime.label_cache_dir(ROOT)
GUARD=threading.RLock()
KINDS=('physics','math','korean')

def normalize_labels(items):
    if not isinstance(items,list) or len(items)>80: raise ValueError('글씨 객체는 최대 80개입니다.')
    out=[]
    for item in items:
        if not isinstance(item,dict): raise ValueError('글씨 객체 형식 오류')
        obj={k:item.get(k) for k in ('id','kind','text','x','y','size','rotation')}
        # Optional metadata preserves older cards and their approval digests.
        if 'name' in item: obj['name']=str(item['name'])[:80]
        if 'visible' in item: obj['visible']=item['visible'] is not False
        if 'locked' in item: obj['locked']=item['locked'] is True
        if not re.fullmatch('[a-f0-9]{16}',str(obj['id'])) or obj['kind'] not in KINDS: raise ValueError('글씨 객체 ID·종류 오류')
        if not isinstance(obj['text'],str) or not obj['text'].strip() or len(obj['text'])>500: raise ValueError('글씨는 1~500자로 입력하세요.')
        for key,lo,hi in [('x',0,1000),('y',0,640),('size',8,120),('rotation',-180,180)]:
            v=obj[key]
            if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError('글씨 위치·크기·회전 범위 오류')
            obj[key]=round(v,3)
        out.append(obj)
    if len({x['id'] for x in out})!=len(out): raise ValueError('글씨 객체 ID 중복')
    return out

def render(kind,text,size):
    item=normalize_labels([dict(id='0'*16,kind=kind,text=text,x=0,y=0,size=size,rotation=0)])[0]
    key=hashlib.sha256(json.dumps([kind,text,item['size'],'v2'],ensure_ascii=False).encode()).hexdigest()
    with GUARD:
        CACHE.mkdir(parents=True,exist_ok=True)
        png=CACHE/(key+'.png'); meta=CACHE/(key+'.json')
        if not png.exists() or not meta.exists():
            request=CACHE/(key+'.request.json')
            request.write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8')
            if kind=='korean':
                proc=subprocess.run([sys.executable,str(ROOT/'app/hwp_label.py'),str(request),str(png)],capture_output=True,encoding='utf-8',errors='replace',timeout=45,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if proc.returncode or not png.exists(): raise ValueError('신명 중명조 렌더링 실패. 설치된 한글을 확인하세요. '+proc.stderr[-500:])
                with Image.open(png) as im: width,height=im.width/3,im.height/3
                font='신명 중명조'
            else:
                if not FONT.exists(): raise ValueError('Latin Modern Math 글꼴 파일이 없습니다.')
                import ziamath
                ziamath.config.svg2=False
                if re.search('[가-힣]',text): raise ValueError('한글은 별도의 한글 객체로 추가하세요.')
                try:
                    svg=ziamath.Latex(text.strip().strip('$'),size=size,font=str(FONT)).svg()
                    root=ET.fromstring(svg); width=float(root.get('width'));height=float(root.get('height'))
                except Exception as e: raise ValueError('수식 표기를 확인하세요: '+str(e)[:180])
                if width>1000 or height>640: raise ValueError('글씨가 캔버스보다 큽니다. 크기를 줄이세요.')
                source=CACHE/(key+'.svg');source.write_text(svg,encoding='utf-8')
                node=runtime.node_executable(ROOT)
                if not node: raise ValueError('SVG 렌더링에 Node.js가 필요합니다.')
                env=runtime.node_environment(ROOT)
                proc=subprocess.run([node,str(ROOT/'app/render_label.cjs'),str(source),str(png)],capture_output=True,encoding='utf-8',env=env,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if proc.returncode: raise ValueError('수식 렌더링 실패: '+proc.stderr[-400:])
                with Image.open(png) as im: width,height=im.width/3,im.height/3
                font='Latin Modern Math'
            if width>1000 or height>640: raise ValueError('글씨가 캔버스보다 큽니다. 크기를 줄이세요.')
            meta.write_text(json.dumps(dict(width=width,height=height,font=font)),encoding='utf-8')
        value=json.loads(meta.read_text(encoding='utf-8'))
        value.update(key=key,url='/label-assets/'+key+'.png')
        return value

def compose(base_path,objects,destination):
    """Use the same transparent glyph bitmaps and top-left coordinates as the editor."""
    with Image.open(base_path) as src: base=src.convert('RGBA').resize((3000,1920),Image.Resampling.LANCZOS)
    for obj in normalize_labels(objects):
        if obj.get('visible',True) is False: continue
        rendered=render(obj['kind'],obj['text'],obj['size'])
        with Image.open(CACHE/(rendered['key']+'.png')) as src: glyph=src.convert('RGBA')
        if obj['rotation']:
            rotated=glyph.rotate(-obj['rotation'],resample=Image.Resampling.BICUBIC,expand=True)
            x=obj['x']*3+(glyph.width-rotated.width)/2;y=obj['y']*3+(glyph.height-rotated.height)/2;glyph=rotated
        else: x=obj['x']*3;y=obj['y']*3
        if x<0 or y<0 or x+glyph.width>3000 or y+glyph.height>1920: raise ValueError('글씨가 그림 밖으로 잘립니다. 위치·크기·회전을 조정하세요: '+obj['text'][:50])
        base.alpha_composite(glyph,(round(x),round(y)))
    base.convert('RGB').save(destination,format='PNG')

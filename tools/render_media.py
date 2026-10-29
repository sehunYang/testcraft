"""Edit real screen recordings, voice-aligned subtitles, music and beat-cut shorts.

Raw captures and editable stems stay under .runtime/media-production. Only the
finished media, captions, posters and manifest are candidates for publication.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.runtime/media-packages'))
import imageio_ffmpeg
from PIL import Image,ImageDraw,ImageFont
from fontTools.ttLib import TTFont

OUT=ROOT/'.runtime/media-production'
FIN=OUT/'finished';WORK=OUT/'work';FIN.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
FF=imageio_ffmpeg.get_ffmpeg_exe()
BASE='https://github.com/sehunYang/testcraft/releases/download/media-v1/'
SCRIPT=json.loads((ROOT/'tools/media-script.json').read_text(encoding='utf-8'))


def run(args):
    r=subprocess.run([FF,'-hide_banner','-loglevel','error','-y',*map(str,args)],cwd=OUT,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8',errors='replace')[-4000:])


def duration(file):
    r=subprocess.run([FF,'-hide_banner','-i',str(file)],capture_output=True)
    m=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',r.stderr.decode(errors='replace'))
    if not m:raise ValueError(str(file))
    h,m,s=map(float,m.groups());return h*3600+m*60+s


def fonts():
    folder=OUT/'fonts';folder.mkdir(exist_ok=True);target=folder/'PretendardGOV.ttf'
    if not target.exists():
        font=TTFont(ROOT/'app/fonts/pretendard-gov/PretendardGOVVariable.woff2');font.flavor=None;font.save(target)
    return target


FONT=fonts()
def stamp(t,ass=False):
    if ass:return f'{int(t//3600)}:{int(t//60)%60:02}:{t%60:05.2f}'
    ms=round(t*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def cues(episode,chapter):
    data=[json.loads(line) for line in (OUT/'voice'/episode/(chapter+'.jsonl')).read_text(encoding='utf-8').splitlines()]
    result=[];group=[]
    for word in data:
        group.append(word)
        if len(' '.join(w['text'] for w in group))>=34 or (word['offset']-group[0]['offset'])/1e7>=4 or word['text'].endswith(('.','?','!')):
            result.append((group[0]['offset']/1e7+.7,(word['offset']+word['duration'])/1e7+.9,' '.join(w['text'] for w in group)));group=[]
    if group:result.append((group[0]['offset']/1e7+.7,(group[-1]['offset']+group[-1]['duration'])/1e7+.9,' '.join(w['text'] for w in group)))
    cleaned=[]
    for i,(start,end,text) in enumerate(result):
        if i+1<len(result):end=min(end,result[i+1][0]-.02)
        for spoken,caption in [('테스트크래프트','TestCraft'),('코덱스 씨엘아이','Codex CLI'),('챗지피티','ChatGPT'),('에이아이','AI'),('에스브이지','SVG'),('스트릭트','strict'),('플렉서블','flexible'),('믹스드','mixed'),('이스케이프','Esc')]:text=text.replace(spoken,caption)
        cleaned.append((start,end,text))
    return cleaned


def ass_file(ep,c,subtitle_cues):
    family=TTFont(FONT)['name'].getDebugName(1)
    lines=['[Script Info]','ScriptType: v4.00+','PlayResX: 1920','PlayResY: 1080','WrapStyle: 0','[V4+ Styles]',
      'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
      f'Style: Default,{family},35,&H00FFFFFF,&H00FFFFFF,&HAA17243C,&HAA17243C,0,0,0,0,100,100,0,0,3,10,0,2,100,100,42,1',
      f'Style: Title,{family},25,&H00FFFFFF,&H00FFFFFF,&HAA17243C,&HAA17243C,0,0,0,0,100,100,0,0,3,10,0,8,100,100,20,1',
      '[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    # Captions are separate VTT/SRT tracks, so users can resize or disable them.
    # Only chapter titles and the honest time-compression notice are burned in.
    lines.append(f'Dialogue: 0,0:00:00.00,0:00:03.00,Title,,0,0,0,,{ep["title"]} · {c["title"]}')
    if c['id']=='generate' and ep['id'] in ('03-author','05-figure','07-export'):
        lines.append('Dialogue: 0,0:00:03.00,0:00:08.00,Title,,0,0,0,,실제 작업 화면 · 대기 구간 단축')
    file=WORK/(ep['id']+'-'+c['id']+'.ass');file.write_text('\n'.join(lines),encoding='utf-8');return file


def chapter_video(ep,c,scene,raw_fallback):
    voice=OUT/'voice'/ep['id']/(c['id']+'.mp3')
    d=max(duration(voice)+1.6,scene['end']-scene['start']+.5)
    sub=cues(ep['id'],c['id']);ass=ass_file(ep,c,sub)
    target=WORK/(ep['id']+'-'+c['id']+'.mp4')
    video=OUT/scene.get('raw',raw_fallback)
    if not target.exists() or target.stat().st_mtime < max(video.stat().st_mtime,voice.stat().st_mtime):
        clip=scene['end']-scene['start']
        run(['-ss',scene['start'],'-t',clip,'-i',video,'-i',voice,'-stream_loop','-1','-i',OUT/'audio/quiet-precision-tutorial.wav',
          '-i',OUT/'audio/sfx/tap.wav',
          '-filter_complex',f'[0:v]setpts=PTS-STARTPTS,scale=1728:1080,pad=1920:1080:96:0:color=0x0e1930,fps=30,tpad=stop_mode=clone:stop_duration={d},trim=duration={d},subtitles={ass.relative_to(OUT).as_posix()}:fontsdir=fonts[v];'
          f'[1:a]adelay=700|700,apad=whole_dur={d},atrim=duration={d},volume=1.8[voice];'
          f'[2:a]atrim=duration={d},volume=0.10,afade=t=in:d=0.5,afade=t=out:st={d-.7}:d=0.7[music];'
          '[3:a]adelay=1100|1100,volume=.18[sfx];[voice][music][sfx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=.92[a]',
          '-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-threads','2',
          '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart','-t',d,target])
    print(f'render {ep["id"]}/{c["id"]} {d:.1f}s',flush=True)
    return {'id':c['id'],'title':c['title'],'duration':d,'text':c['text'],'cues':sub,'file':target}


def poster(ep,scene):
    img=Image.open(OUT/scene['still']).convert('RGB').resize((1600,1000))
    shade=Image.new('RGBA',img.size,(0,0,0,0));draw=ImageDraw.Draw(shade)
    draw.rectangle((0,0,1600,200),fill=(15,29,57,232))
    draw.text((55,35),'TESTCRAFT  /  처음부터 시험지까지',font=ImageFont.truetype(FONT,24),fill='#adc0ff')
    draw.text((55,85),ep['title'],font=ImageFont.truetype(FONT,54),fill='white')
    img=Image.alpha_composite(img.convert('RGBA'),shade).convert('RGB');img.save(FIN/(ep['id']+'.jpg'),quality=87)


def tutorials(capture):
    catalog={'version':1,'app_version':'1.1.2','recorded_at':'2026-10-29','music':SCRIPT['music'],'episodes':[]}
    for ep in SCRIPT['episodes']:
        scenes={s['id']:s for s in capture['scenes'] if s['episode']==ep['id']}
        if any(c['id'] not in scenes for c in ep['chapters']):raise ValueError('Missing recorded scene: '+ep['id'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            parts=list(pool.map(lambda c:chapter_video(ep,c,scenes[c['id']],capture['raw']),ep['chapters']))
        concat=WORK/(ep['id']+'-concat.txt');concat.write_text('\n'.join("file '"+str(p['file']).replace('\\','/')+"'" for p in parts),encoding='utf-8')
        result=FIN/(ep['id']+'.mp4')
        run(['-f','concat','-safe','0','-i',concat,'-c','copy','-movflags','+faststart',result])
        offset=0;vtt=['WEBVTT',''];srt=[];chapters=[];cue_index=0
        for p in parts:
            chapters.append({k:p[k] for k in ('id','title','text')}|{'start':round(offset,3)})
            for start,end,text in p['cues']:
                vtt.extend([f'{stamp(offset+start)} --> {stamp(offset+end)}',text,''])
                cue_index+=1;srt.extend([str(cue_index),f'{stamp(offset+start).replace(".",",")} --> {stamp(offset+end).replace(".",",")}',text,''])
            offset+=p['duration']
        (FIN/(ep['id']+'.vtt')).write_text('\n'.join(vtt),encoding='utf-8')
        (FIN/(ep['id']+'.srt')).write_text('\n'.join(srt),encoding='utf-8')
        poster(ep,scenes[ep['chapters'][0]['id']])
        catalog['episodes'].append({'id':ep['id'],'title':ep['title'],'stage':ep['stage'],'duration':round(offset,2),
          'description':'공개용 예제 시험 · 실제 앱 조작 · 한국어 설명과 자막',
          'video':BASE+ep['id']+'.mp4','poster':'./media/'+ep['id']+'.jpg','captions':'/tutorials/'+ep['id']+'.vtt','chapters':chapters})
    (FIN/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'app/static/tutorials-manifest.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    app_subs=ROOT/'app/static/tutorials';app_subs.mkdir(exist_ok=True)
    site=ROOT/'docs/media';site.mkdir(exist_ok=True)
    for ep in catalog['episodes']:
        shutil.copy2(FIN/(ep['id']+'.vtt'),app_subs)
        shutil.copy2(FIN/(ep['id']+'.vtt'),site)
        shutil.copy2(FIN/(ep['id']+'.jpg'),site)
    (site/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    return catalog


def short_overlay(title,subtitle,index,portrait=True):
    size=(1080,1920) if portrait else (1920,1080)
    image=Image.new('RGBA',size,(245,247,252,255));draw=ImageDraw.Draw(image)
    logo=Image.open(ROOT/'app/static/icons/icon-192.png').convert('RGBA').resize((76,76))
    image.alpha_composite(logo,(65,70));draw.text((155,79),'TestCraft',font=ImageFont.truetype(FONT,48),fill='#274bd0')
    if portrait:
        draw.text((70,255),f'0{index+1} / THE WORKSHOP',font=ImageFont.truetype(FONT,25),fill='#365eef')
        for i,line in enumerate(title.split('\n')):draw.text((65,320+i*108),line,font=ImageFont.truetype(FONT,84),fill='#17243c')
        draw.text((70,1510),subtitle,font=ImageFont.truetype(FONT,31),fill='#536780')
        draw.line((70,1630,1010,1630),fill='#d8e1f1',width=2)
        draw.text((70,1680),'평가의 의도를 담아,\n시험을 빚다.',font=ImageFont.truetype(FONT,39),fill='#17243c',spacing=12)
        draw.rounded_rectangle((70,1820,70+int(940*(index+1)/6),1827),radius=3,fill='#365eef')
        draw.rectangle((44,570,1036,1464),fill=(0,0,0,0))
    return image


def promos(capture):
    lookup={(s['episode'],s['id']):s for s in capture['scenes']}
    cuts=[('07-export','documents',3.75,'아이디어가\n시험지가 되다.','교사를 위한 시험공방'),
          ('02-design','criteria',7.5,'출제 의도를\n입력하세요.','성취기준 · 유형 · 난이도 · 아이디어'),
          ('03-author','generate',3.75,'초안은 AI와\n함께.','실제 생성 화면 · 대기 구간 단축'),
          ('06-editor','snap',7.5,'한 장의 그림도\n정교하게.','객체 편집 · 15° 회전 · 독립 글씨'),
          ('07-export','documents',3.75,'한글 시험지로\n완성하세요.','학생용 · 교사용 · 정답과 해설'),
          ('06-editor','final',3.75,'TestCraft','지금, 나만의 시험공방을 여세요.')]
    files=[]
    for i,(eid,cid,d,title,subtitle) in enumerate(cuts):
        scene=lookup[eid,cid];overlay=WORK/f'short-overlay-{i}.png';short_overlay(title,subtitle,i).save(overlay)
        target=WORK/f'short-{i}.mp4';raw=OUT/scene.get('raw',capture['raw']);clip=min(scene['end']-scene['start'],d)
        run(['-ss',scene['start'],'-t',clip,'-i',raw,'-loop','1','-i',overlay,
          '-filter_complex',f'[0:v]setpts=PTS-STARTPTS,crop=1100:990:250:0,scale=992:893,fps=30,tpad=stop_mode=clone:stop_duration={d},trim=duration={d}[screen];[1:v][screen]overlay=44:570:shortest=1,format=yuv420p[v]',
          '-map','[v]','-an','-t',d,'-c:v','libx264','-preset','veryfast','-crf','22','-threads','2',target]);files.append(target)
    concat=WORK/'short-concat.txt';concat.write_text('\n'.join("file '"+str(p).replace('\\','/')+"'" for p in files),encoding='utf-8')
    run(['-f','concat','-safe','0','-i',concat,'-i',OUT/'audio/quiet-precision-reprise.wav',
      '-i',OUT/'audio/sfx/snap.wav','-filter_complex','[2:a]adelay=15000|15000,volume=.3[s];[1:a][s]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=8[a]',
      '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-t','30','-movflags','+faststart',FIN/'testcraft-short.mp4'])
    run(['-i',FIN/'testcraft-short.mp4','-frames:v','1',FIN/'testcraft-short.jpg'])
    # 8 bars at 128 BPM = 15 seconds. Homepage version is intentionally silent.
    loops=[]
    for i,(eid,cid) in enumerate([('02-design','criteria'),('06-editor','objects'),('06-editor','snap'),('07-export','documents')]):
        scene=lookup[eid,cid];target=WORK/f'loop-{i}.mp4';clip=min(3.75,scene['end']-scene['start'])
        run(['-ss',scene['start'],'-t',clip,'-i',OUT/scene.get('raw',capture['raw']),'-vf','setpts=PTS-STARTPTS,scale=1280:800,pad=1280:800,fps=30,tpad=stop_mode=clone:stop_duration=4,trim=duration=3.75',
          '-an','-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p','-threads','2',target]);loops.append(target)
    concat=WORK/'loop-concat.txt';concat.write_text('\n'.join("file '"+str(p).replace('\\','/')+"'" for p in loops),encoding='utf-8')
    run(['-f','concat','-safe','0','-i',concat,'-c','copy','-an','-movflags','+faststart',FIN/'testcraft-loop.mp4'])
    shutil.copy2(FIN/'testcraft-short.jpg',ROOT/'docs/media/testcraft-short.jpg')
    # Small, silent hero video is versioned with Pages for reliable autoplay.
    shutil.copy2(FIN/'testcraft-loop.mp4',ROOT/'docs/media/testcraft-loop.mp4')
    for name in ('quiet-precision-tutorial','quiet-precision-reprise'):
        shutil.copy2(OUT/'audio'/(name+'.mp3'),FIN)
    shutil.copy2(OUT/'audio/composition.json',FIN)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--promos-only',action='store_true');parser.add_argument('--captions-only',action='store_true');args=parser.parse_args()
    capture=json.loads((OUT/'capture.json').read_text(encoding='utf-8'))
    if any('raw' not in s for s in capture['scenes']):raise ValueError('Each scene must identify its original recording.')
    if not args.promos_only:tutorials(capture)
    if not args.captions_only:promos(capture)
    print('Finished media:',FIN,flush=True)

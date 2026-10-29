"""Validate finished media, subtitles, fast-start MP4 and the actual HWPX example."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/media-packages'))
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.runtime/media-production';FIN=OUT/'finished';FF=imageio_ffmpeg.get_ffmpeg_exe()

def seconds(text):
    h,m,s=map(float,text.split(':'));return h*3600+m*60+s

def main():
    catalog=json.loads((FIN/'catalog.json').read_text(encoding='utf-8'));assert len(catalog['episodes'])==7
    result=[]
    files=[FIN/(e['id']+'.mp4') for e in catalog['episodes']]+[FIN/'testcraft-short.mp4',FIN/'testcraft-loop.mp4']
    for file in files:
        probe=subprocess.run([FF,'-hide_banner','-i',str(file)],capture_output=True).stderr.decode(errors='replace')
        d=seconds(re.search(r'Duration: (\d+:\d+:\d+\.\d+)',probe).group(1))
        assert 'h264' in probe and 'yuv420p' in probe
        assert ('Audio:' in probe)==(file.name!='testcraft-loop.mp4')
        data=file.read_bytes();assert data.find(b'moov')<data.find(b'mdat'),'MP4 is not fast-start'
        decode=subprocess.run([FF,'-v','error','-i',str(file),'-f','null','-'],capture_output=True)
        assert decode.returncode==0 and not decode.stderr,decode.stderr
        item={'file':file.name,'duration':d,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'decode':'passed'}
        if file.stem.startswith(('01','02','03','04','05','06','07')):
            ep=next(e for e in catalog['episodes'] if e['id']==file.stem);assert abs(d-ep['duration'])<1
            assert ep['chapters'][0]['start']==0
            ranges=re.findall(r'(\d+:\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+)',(FIN/(ep['id']+'.vtt')).read_text(encoding='utf-8'))
            assert len(ranges)>8
            previous=0
            for start,end in ranges:
                a,b=seconds(start),seconds(end);assert 0<=a<b<=d+.2 and a>=previous-.3;previous=b
            item['subtitle_cues']=len(ranges)
        if file.name=='testcraft-short.mp4':assert abs(d-30)<.1
        if file.name=='testcraft-loop.mp4':assert abs(d-15)<.1
        result.append(item);print('verified',file.name,d,flush=True)
    sys.path[:0]=[str(ROOT),str(ROOT/'.runtime/packages')]
    from app.hwpx import validate_hwpx_package
    exam=json.loads((OUT/'final-exam.json').read_text(encoding='utf-8'));bundle=exam['exports'][-1]
    folder=OUT/'exams'/exam['id']/'exports'/bundle['id']
    hwpx={name:validate_hwpx_package(folder/name,folder/Path(name).with_suffix('.hml')) for name in ('시험지_학생용.hwpx','시험지_교사용.hwpx','정답과해설.hwpx')}
    report={'videos':result,'hwpx':hwpx,'all_passed':True}
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('All media and actual HWPX output verified.')

if __name__=='__main__':main()

"""Compose original music/SFX and render the public Korean narration script.

All musical sounds are synthesized here; no third-party samples or songs.
Run with media_requirements.txt available on PYTHONPATH. Stems remain editable.
"""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.runtime/media-packages'))
import numpy as np
import imageio_ffmpeg

OUT = ROOT / '.runtime/media-production'
FF = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000
RNG = np.random.default_rng(108128)


def wav(path, audio):
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.ndim == 1:
        audio = np.column_stack([audio, audio])
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes((np.clip(audio, -.98, .98) * 32767).astype('<i2').tobytes())


def add(track, sound, when, volume=1., pan=0.):
    start = int(when * SR)
    if start >= len(track): return
    sound = sound[:len(track)-start]
    track[start:start+len(sound), 0] += sound * volume * np.sqrt((1-pan)/2)
    track[start:start+len(sound), 1] += sound * volume * np.sqrt((1+pan)/2)


def tone(note, seconds, kind='keys'):
    t = np.arange(int(seconds * SR)) / SR
    hz = 440 * 2 ** ((note - 69) / 12)
    if kind == 'keys':
        signal = (np.sin(2*np.pi*hz*t + .7*np.sin(2*np.pi*hz*2*t)*np.exp(-t*5))
                  + .22*np.sin(2*np.pi*hz*2*t)*np.exp(-t*3)
                  + .06*np.sin(2*np.pi*hz*4*t)*np.exp(-t*5))
        env = (1-np.exp(-t*180)) * np.exp(-t*2.4)
    elif kind == 'bass':
        signal = np.sin(2*np.pi*hz*t) + .19*np.sin(4*np.pi*hz*t)
        env = np.minimum(t/.008, 1) * np.minimum((seconds-t)/.06, 1)
    else:
        signal = np.sin(2*np.pi*hz*t) + .09*np.sin(2*np.pi*hz*2.003*t)
        env = np.minimum(t/.3,1) * np.minimum((seconds-t)/.5,1)
    return signal * np.maximum(env, 0)


def compose(name, bpm, bars):
    beat = 60 / bpm
    duration = bars*4*beat
    tracks = {key: np.zeros((round(duration*SR),2), np.float32) for key in ('drums','bass','harmony','motif')}
    fast = bpm > 120
    chords = [(50,57,60,64,69),(53,60,64,67,72),(48,55,59,62,67),(43,53,57,62,65)]
    for bar in range(bars):
        start = bar*4*beat
        chord = chords[(bar//4)%4]
        energy = (0.68 if bar < 2 or bar >= bars-2 else 1.) if fast else .6
        for i,n in enumerate(chord):
            add(tracks['harmony'], tone(n, 4*beat+1,'pad'), start, .045*energy, (i-2)*.24)
            add(tracks['harmony'], tone(n+12, 1.5), start+(.5 if fast else 1)*beat, .055*energy, (i-2)*.25)
        for b in range(4):
            now = start+b*beat
            t=np.arange(int(.32*SR))/SR
            phase=2*np.pi*(48*t+85*.024*(1-np.exp(-t/.024)))
            kick=np.sin(phase)*(1-np.exp(-t*1500))*np.exp(-t*18)
            add(tracks['drums'],kick,now,.46*energy)
            t=np.arange(int(.09*SR))/SR
            noise=RNG.normal(0,1,len(t));noise=np.diff(noise,prepend=0)
            add(tracks['drums'],noise*np.exp(-t*65),now+beat*.5,.025*energy,.28)
            if b in (1,3):
                t=np.arange(int(.14*SR))/SR
                clap=RNG.normal(0,1,len(t))*np.exp(-t*38)
                add(tracks['drums'],clap,now,.025*energy,-.16)
            add(tracks['bass'],tone(chord[0]-12,beat*.64,'bass'),now+beat*.5,.22*energy)
        if bar % 4 in (0,2) or fast:
            for i,n in enumerate([74,77,81,76]):
                at=start+([0,1.5,2.5,3.25][i] if fast else [0,1,2.5,3.25][i])*beat
                add(tracks['motif'],tone(n,.9),at,.10*energy,[-.25,.2,-.1,.3][i])
    mix=np.zeros_like(tracks['drums'])
    for name_key,audio in tracks.items():
        if name_key in ('harmony','motif'):
            # Quiet stereo echoes; no external reverb/sample dependencies.
            for delay,gain in [(beat*.75,.17),(beat*1.5,.08)]:
                count=round(delay*SR)
                audio[count:]+=audio[:-count,::-1]*gain
        if name_key!='drums':
            phase=(np.arange(len(audio))/SR)%beat
            audio*= (1-.27*np.exp(-phase/.07))[:,None]
        wav(OUT/'audio/stems'/f'{name}-{name_key}.wav',audio)
        mix+=audio
    peak=float(np.max(np.abs(mix)))
    mix*=.78/max(peak,.78)
    # Fade only the long tutorial master; the short has an intentional final cadence.
    count=int(.08*SR)
    mix[:count]*=np.linspace(0,1,count)[:,None]
    mix[-int(.3*SR):]*=np.linspace(1,0,int(.3*SR))[:,None]
    master=OUT/'audio'/f'{name}.wav';wav(master,mix)
    subprocess.run([FF,'-v','error','-y','-i',str(master),'-codec:a','libmp3lame','-b:a','192k',str(master.with_suffix('.mp3'))],check=True)
    print(json.dumps({'track':name,'bpm':bpm,'duration':duration,'peak':float(np.max(np.abs(mix)))}),flush=True)


def effects():
    for name,notes in [('tap',[81]),('snap',[86,93]),('complete',[74,77,81,88])]:
        audio=np.zeros((SR,2),np.float32)
        for i,n in enumerate(notes):add(audio,tone(n,.35),i*.075,.24,-.2+i*.1)
        wav(OUT/'audio/sfx'/f'{name}.wav',audio)
    (OUT/'audio/composition.json').write_text(json.dumps({
        'title':'Quiet Precision','composer':'TestCraft production · original algorithmic composition',
        'key':'D minor / extended seventh and ninth chords','motif':['D5','F5','A5','E5'],
        'tutorial_bpm':108,'short_bpm':128,'source':'tools/build_media_audio.py',
        'samples':'none; all oscillators, envelopes and percussion synthesized from source',
        'license':'CC BY 4.0; attribution: TestCraft / sehunYang'
    },ensure_ascii=False,indent=2),encoding='utf-8')


async def voices():
    import edge_tts
    script=json.loads((ROOT/'tools/media-script.json').read_text(encoding='utf-8'))
    semaphore=asyncio.Semaphore(2)
    async def one(ep,chapter):
        path=OUT/'voice'/ep['id']/(chapter['id']+'.mp3');path.parent.mkdir(parents=True,exist_ok=True)
        metadata=path.with_suffix('.jsonl')
        if path.exists() and path.stat().st_size>1000 and metadata.exists():return
        async with semaphore:
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(chapter['text'],script['voice'],rate='-5%',boundary='WordBoundary').save(str(path),str(metadata))
                    print(f"voice {ep['id']}/{chapter['id']}",flush=True);return
                except Exception:
                    if attempt==2:raise
                    await asyncio.sleep(2)
    await asyncio.gather(*(one(e,c) for e in script['episodes'] for c in e['chapters']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--voice-only',action='store_true');args=parser.parse_args()
    if not args.voice_only:
        compose('quiet-precision-tutorial',108,32);compose('quiet-precision-reprise',128,16);effects()
    asyncio.run(voices())

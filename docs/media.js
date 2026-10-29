'use strict';
(()=>{
 const base='https://github.com/sehunYang/testcraft/releases/download/media-v1/';
 const hero=document.querySelector('#heroLoop'),toggle=document.querySelector('#heroMotionToggle');
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');let stopped=reduced.matches||navigator.connection?.saveData===true,visible=false;
 function label(){toggle.textContent=hero.paused?'▶ 재생':'Ⅱ 일시정지';toggle.setAttribute('aria-label',hero.paused?'작업실 시연 영상 재생':'작업실 시연 영상 일시정지')}
 function playback(){if(visible&&!stopped&&!document.hidden&&!document.querySelector('#shortDialog[open]')){hero.muted=true;hero.play().catch(label)}else hero.pause();label()}
 toggle.onclick=()=>{stopped=!hero.paused;playback()};hero.addEventListener('play',label);hero.addEventListener('pause',label);
 hero.addEventListener('error',()=>{hero.hidden=true;document.querySelector('#heroMotionPoster').hidden=false;toggle.hidden=true});
 new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;playback()},{threshold:.15}).observe(hero);
 document.addEventListener('visibilitychange',playback);reduced.addEventListener('change',e=>{stopped=e.matches;playback()});
 const video=document.querySelector('#siteTutorialVideo'),list=document.querySelector('#siteTutorialList');
 const make=(tag,props={})=>Object.assign(document.createElement(tag),props);
 function safeVideo(url){try{const u=new URL(url);return u.href.startsWith(base)&&u.origin==='https://github.com'&&!u.username&&!u.password}catch{return false}}
 function choose(ep,button){
  video.pause();video.replaceChildren();video.src=ep.video;video.poster='./media/'+ep.id+'.jpg';
  video.append(make('track',{kind:'subtitles',label:'한국어',srclang:'ko',src:'./media/'+ep.id+'.vtt',default:true}));video.load();
  document.querySelector('#siteTutorialTitle').textContent=ep.title;
  document.querySelector('#siteTutorialDescription').textContent=ep.description;
  document.querySelector('#siteTutorialDownload').href=ep.video;
  list.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',String(b===button)));
  const chapters=document.querySelector('#siteTutorialChapters');chapters.replaceChildren();
  ep.chapters.forEach(c=>{const li=make('li'),b=make('button',{textContent:c.title,type:'button'});b.onclick=()=>{if(video.readyState>=1)video.currentTime=c.start;else video.addEventListener('loadedmetadata',()=>{video.currentTime=c.start},{once:true});video.play().catch(()=>{})};li.append(b);chapters.append(li)});
  const transcript=document.querySelector('#siteTutorialTranscript');transcript.replaceChildren();ep.chapters.forEach(c=>transcript.append(make('b',{textContent:c.title}),make('p',{textContent:c.text})));
  document.querySelector('#siteTutorialError').hidden=true;
 }
 video.addEventListener('error',()=>{document.querySelector('#siteTutorialError').hidden=false});
 fetch('./media/catalog.json').then(r=>{if(!r.ok)throw Error('catalog');return r.json()}).then(c=>{
  if(!Array.isArray(c.episodes)||c.episodes.length!==7||c.episodes.some(e=>!safeVideo(e.video)))throw Error('catalog');
  list.replaceChildren();c.episodes.forEach((ep,i)=>{const li=make('li'),b=make('button',{type:'button'}),text=make('span',{textContent:ep.title});text.append(make('small',{textContent:`${Math.floor(ep.duration/60)}분 ${Math.round(ep.duration%60)}초 · 한국어 설명·자막`}));b.append(make('span',{className:'tutorial-no',textContent:String(i+1).padStart(2,'0')}),text);b.onclick=()=>choose(ep,b);li.append(b);list.append(li);if(!i)choose(ep,b)});
 }).catch(()=>{document.querySelector('#siteTutorialError').hidden=false});
 const dialog=document.querySelector('#shortDialog'),short=dialog.querySelector('video');
 document.querySelector('#watchShort').onclick=()=>{hero.pause();video.pause();dialog.showModal();short.src=base+'testcraft-short.mp4';short.play().catch(()=>{})};
 dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{short.pause();playback()});
})();

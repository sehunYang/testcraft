'use strict';
// 과목별 예시 문항 둘러보기와 출력 파일 예시 창.
(()=>{
 const make=(tag,props={},...kids)=>{const el=Object.assign(document.createElement(tag),props);el.append(...kids);return el};
 const WRITTEN=['단답형','서술형','논술형'];
 // 0) 크게 보기 창: 두 손가락 벌리기(핀치), Ctrl+휠, 버튼, 두 번 누르기로 확대한다. 확대하면 끌거나 스크롤해 옮긴다.
 let zoomDialog,zoomImg,zoomBox,zoomLabel,scale=1;
 function setScale(next,cx,cy){
  next=Math.min(5,Math.max(1,next));if(!zoomBox)return;
  const r=zoomBox.getBoundingClientRect();cx=cx??r.left+r.width/2;cy=cy??r.top+r.height/2;
  const fx=(zoomBox.scrollLeft+cx-r.left)/zoomImg.offsetWidth,fy=(zoomBox.scrollTop+cy-r.top)/zoomImg.offsetHeight;
  scale=next;zoomImg.style.width=scale*100+'%';
  zoomBox.scrollLeft=fx*zoomImg.offsetWidth-(cx-r.left);zoomBox.scrollTop=fy*zoomImg.offsetHeight-(cy-r.top);
  zoomLabel.textContent=Math.round(scale*100)+'%';zoomBox.classList.toggle('is-zoomed',scale>1);
 }
 function buildZoom(){
  zoomImg=make('img',{alt:'',draggable:false});zoomBox=make('div',{className:'zoom-box',tabIndex:0},zoomImg);zoomLabel=make('span',{className:'zoom-level',textContent:'100%'});
  const title=make('b',{className:'zoom-title'}),btn=(text,label,fn)=>{const b=make('button',{type:'button',textContent:text});b.setAttribute('aria-label',label);b.onclick=fn;return b};
  const bar=make('div',{className:'zoom-bar'},title,btn('−','축소',()=>setScale(scale-.5)),zoomLabel,btn('＋','확대',()=>setScale(scale+.5)),btn('맞춤','화면에 맞춤',()=>setScale(1)),btn('×','닫기',()=>zoomDialog.close()));
  zoomDialog=make('dialog',{className:'zoom-dialog'},bar,zoomBox,make('p',{className:'zoom-hint',textContent:'두 손가락으로 벌리거나 Ctrl+휠, ＋ 버튼으로 확대합니다. 두 번 누르면 2배로 봅니다.'}));
  zoomDialog.setAttribute('aria-label','시험지 크게 보기');document.body.append(zoomDialog);
  zoomDialog.addEventListener('click',e=>{if(e.target===zoomDialog)zoomDialog.close()});
  zoomBox.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();setScale(scale*(e.deltaY<0?1.15:1/1.15),e.clientX,e.clientY)},{passive:false});
  zoomBox.addEventListener('dblclick',e=>setScale(scale>1?1:2,e.clientX,e.clientY));
  const points=new Map();let startDist=0,startScale=1,drag=null;
  const dist=()=>{const [a,b]=[...points.values()];return Math.hypot(a.x-b.x,a.y-b.y)};
  zoomBox.addEventListener('pointerdown',e=>{points.set(e.pointerId,{x:e.clientX,y:e.clientY});
   if(points.size===2){startDist=dist();startScale=scale;drag=null}
   else if(e.pointerType==='mouse'&&scale>1){drag={x:e.clientX,y:e.clientY,l:zoomBox.scrollLeft,t:zoomBox.scrollTop};zoomBox.setPointerCapture(e.pointerId)}});
  zoomBox.addEventListener('pointermove',e=>{if(!points.has(e.pointerId))return;points.set(e.pointerId,{x:e.clientX,y:e.clientY});
   if(points.size===2&&startDist){const [a,b]=[...points.values()];setScale(startScale*dist()/startDist,(a.x+b.x)/2,(a.y+b.y)/2)}
   else if(drag){zoomBox.scrollLeft=drag.l-(e.clientX-drag.x);zoomBox.scrollTop=drag.t-(e.clientY-drag.y)}});
  const up=e=>{points.delete(e.pointerId);if(points.size<2)startDist=0;drag=null};
  zoomBox.addEventListener('pointerup',up);zoomBox.addEventListener('pointercancel',up);
  zoomDialog.zoomTitle=title;
 }
 function openZoom(src,alt,title){if(!zoomDialog)buildZoom();zoomImg.src=src;zoomImg.alt=alt;zoomDialog.zoomTitle.textContent=title;zoomDialog.showModal();setScale(1);zoomBox.scrollTop=0;zoomBox.focus()}
 // 1) 과목별 예시 문항
 const root=document.querySelector('#examples');
 if(root)fetch(new URL('./assets/examples/index.json',document.baseURI)).then(r=>{if(!r.ok)throw Error();return r.json()}).then(data=>{
  const groups=root.querySelector('.examples-groups'),subjects=root.querySelector('.examples-subjects'),pages=root.querySelector('.examples-pages'),ideas=root.querySelector('.examples-ideas');
  function showSubject(item,button){
   subjects.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
   pages.replaceChildren(...item.pages.map((file,i)=>{const img=make('img',{src:`./assets/examples/${file}`,alt:`${item.title} 예시 시험지 ${i+1}쪽`,loading:'lazy',width:1600,height:2263});const b=make('button',{type:'button',className:'examples-page',title:'눌러서 크게 보기'},img,make('span',{textContent:'크게 보기'}));b.onclick=()=>openZoom(img.src,img.alt,`${item.title} · ${i+1}쪽`);return b}));pages.scrollTop=0;
   ideas.replaceChildren(...item.cards.map(c=>make('li',{},make('div',{className:'examples-idea-meta'},make('b',{textContent:WRITTEN.includes(c.type)?'서답형':`${c.no}번`}),make('span',{textContent:c.type}),make('span',{textContent:`난이도 ${c.difficulty}`})),make('p',{textContent:c.idea}))));
  }
  function showGroup(g,button){
   groups.querySelectorAll('button').forEach(b=>b.setAttribute('aria-selected',String(b===button)));
   const buttons=g.items.map(item=>{const b=make('button',{type:'button',textContent:item.title});b.onclick=()=>showSubject(item,b);return b});
   subjects.replaceChildren(...buttons);
   const first=Math.max(0,g.items.findIndex(i=>i.id==='physics'));showSubject(g.items[first],buttons[first]);
  }
  const tabs=data.groups.map(g=>{const b=make('button',{type:'button',role:'tab',textContent:g.group});b.append(make('small',{textContent:`${g.items.length}과목`}));b.onclick=()=>showGroup(g,b);return b});
  groups.replaceChildren(...tabs);
  const start=Math.max(0,data.groups.findIndex(g=>g.group==='과학'));showGroup(data.groups[start],tabs[start]);
 }).catch(()=>{root.querySelector('.examples-view').replaceChildren(make('p',{className:'image-note',textContent:'예시 문항을 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.'}))});
 // 2) 출력 파일 예시 창
 const dialog=document.querySelector('#outputDialog');if(!dialog)return;
 const title=dialog.querySelector('h3'),tabs=dialog.querySelector('.output-dialog-tabs'),img=dialog.querySelector('.output-dialog-body img'),table=dialog.querySelector('.output-card-table'),body=dialog.querySelector('.output-dialog-body');
 const VIEWS={
  exam:{title:'학생용 · 교사용 시험지',tabs:[['학생용','student-1.webp','학생용 시험지 예시'],['교사용 (정답 형광펜)','teacher-1.webp','교사용 시험지 예시: 정답에 형광펜 표시']]},
  answers:{title:'정답과 해설',tabs:[['1쪽','answers-1.webp','정답과 해설 예시 1쪽'],['2쪽','answers-2.webp','정답과 해설 예시 2쪽']]},
  card:{title:'문항카드',tabs:[]}};
 function pick(view,i){tabs.querySelectorAll('button').forEach((b,k)=>b.setAttribute('aria-pressed',String(k===i)));const [,file,alt]=view.tabs[i];img.src=`./assets/output/${file}`;img.alt=alt;body.scrollTop=0}
 document.querySelectorAll('[data-output]').forEach(button=>button.addEventListener('click',()=>{
  const view=VIEWS[button.dataset.output];title.textContent=view.title;
  tabs.replaceChildren(...view.tabs.map(([label],i)=>{const b=make('button',{type:'button',textContent:label});b.onclick=()=>pick(view,i);return b}));
  tabs.hidden=!view.tabs.length;img.hidden=!view.tabs.length;table.hidden=!!view.tabs.length;
  if(view.tabs.length)pick(view,0);dialog.showModal();
 }));
 img.title='눌러서 크게 보기';img.addEventListener('click',()=>{const src=img.src,alt=img.alt,t=title.textContent;dialog.close();openZoom(src,alt,t)});
 dialog.querySelector('.output-dialog-close').onclick=()=>dialog.close();
 dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
})();

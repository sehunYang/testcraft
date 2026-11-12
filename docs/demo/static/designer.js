'use strict';
// SVG-Edit math + command history adapted to our separate geometry/text document.
const designer={key:null,tool:'select',labels:new Set(),history:new SvgEditCore.UndoManager(),before:null,drag:null,clipboard:null,space:false,guides:[],snap:true,fieldKey:null};
function designSnapshot(){const c=current();return JSON.stringify({scene:c.image_scene,labels:c.image_labels||[],initialized:c.labels_initialized})}
function designRestore(value){const c=current(),d=JSON.parse(value);c.image_scene=d.scene;c.image_labels=d.labels;c.labels_initialized=d.initialized;ve.selected.clear();designer.labels.clear();selectedLabel=null;vdirty();render()}
function designBegin(){if(current()&&$('#layerCanvas')&&!designer.before)designer.before=designSnapshot()}
function designCommit(key=''){
 if(!designer.before||!current())return;
 const before=designer.before,after=designSnapshot();designer.before=null;
 if(before===after)return;
 const history=designer.history,last=history.undoStack[history.undoStackPointer-1];
 if(key&&last?.key===key&&Date.now()-last.time<900&&history.getRedoStackSize()===0){last.after=after;last.time=Date.now()}
 else history.addCommandToHistory({before,after,key,time:Date.now(),getText(){return '그림·글씨 편집'},apply(){designRestore(this.after)},unapply(){designRestore(this.before)}});
 if(history.undoStack.length>80){history.undoStack.shift();history.undoStackPointer--}
 designPanels();
}
function designHistory(action){designCommit();designer.history[action]();designPanels()}
// Existing geometry operations and new text operations now share one history.
vcheckpoint=()=>designBegin();
const designBaseAction=vaction;
vaction=async function(action){if(state.job?.status==='running')throw Error('생성 완료 후 편집하세요.');if(action==='undo'||action==='redo'){designHistory(action);return}designBegin();await designBaseAction(action);designCommit()};
function designItems(){return [...vselected().map(o=>({kind:'shape',o})),...(current()?.image_labels||[]).filter(o=>designer.labels.has(o.id)).map(o=>({kind:'label',o}))]}
function designLabelBox(o){const g=glyphCache.get(glyphKey(o)),w=g?.width||120,h=g?.height||o.size;const m=new DOMMatrix().translate(o.x+w/2,o.y+h/2).rotate(o.rotation).translate(-w/2,-h/2);const b=SvgEditCore.transformBox(0,0,w,h,m).aabox;return {x:b.x,y:b.y,w:b.width,h:b.height}}
function designBox(item){return item.kind==='shape'?vbox(item.o):designLabelBox(item.o)}
function designUnion(items=designItems()){const boxes=items.map(designBox).filter(Boolean);if(!boxes.length)return null;const x=Math.min(...boxes.map(b=>b.x)),y=Math.min(...boxes.map(b=>b.y));return {x,y,w:Math.max(...boxes.map(b=>b.x+b.w))-x,h:Math.max(...boxes.map(b=>b.y+b.h))-y}}
function designMove(item,dx,dy){if(item.kind==='shape')item.o.matrix=va(new DOMMatrix().translate(dx,dy).multiply(vm(item.o.matrix)));else{item.o.x=Math.max(0,Math.min(1000,item.o.x+dx));item.o.y=Math.max(0,Math.min(640,item.o.y+dy))}}
function designClear(){ve.selected.clear();designer.labels.clear();selectedLabel=null}
function designSelect(kind,id,add=false){if(!add)designClear();const set=kind==='shape'?ve.selected:designer.labels;if(add&&set.has(id))set.delete(id);else set.add(id);selectedLabel=designer.labels.size===1?[...designer.labels][0]:null}
function designRefresh(){selectedLabel=designer.labels.size===1?[...designer.labels][0]:null;vrefresh();renderLabelProperties();designPanels()}
function designLayerRowMarkup(kind,o){const selected=kind==='shape'?ve.selected.has(o.id):designer.labels.has(o.id),name=kind==='shape'?o.name:o.name||o.text;return `<div class="design-layer ${selected?'selected':''}" draggable="true" data-design-row="${esc(o.id)}" data-kind="${kind}"><button data-design-select="${esc(o.id)}" data-kind="${kind}" title="${esc(name)}" aria-pressed="${selected}"><span>${kind==='shape'?'◇':'T'}</span> ${esc(name)}</button><button data-design-toggle="visible" data-id="${esc(o.id)}" data-kind="${kind}" aria-label="${esc(name)} ${o.visible===false?'표시':'숨기기'}" title="표시/숨기기">${o.visible===false?'○':'●'}</button><button data-design-toggle="locked" data-id="${esc(o.id)}" data-kind="${kind}" aria-label="${esc(name)} ${o.locked?'잠금 해제':'잠금'}" title="잠금/해제">${o.locked?'🔒':'◇'}</button></div>`}
function designSyncLayerGroup(list,kind,items){
 const group=list.querySelector(`[data-layer-list="${kind}"]`),count=list.querySelector(`[data-layer-heading="${kind}"] span`);if(!group||!count)return;
 count.textContent=items.length;
 const existing=[...group.children];
 if(existing.length!==items.length||existing.some((row,index)=>row.dataset.kind!==kind||row.dataset.designRow!==items[index]?.id))group.innerHTML=items.map(item=>designLayerRowMarkup(kind,item)).join('')||`<p class="hint">${kind==='label'?'글씨 도구로 추가하세요.':'그림을 객체로 변환하면 목록에 나타납니다.'}</p>`;
 const rows=[...group.querySelectorAll('[data-design-row]')];
 for(let index=0;index<items.length;index++){
  const item=items[index],row=rows[index],selected=kind==='shape'?ve.selected.has(item.id):designer.labels.has(item.id),name=kind==='shape'?item.name:item.name||item.text;
  row.classList.toggle('selected',selected);const button=row.querySelector('[data-design-select]');button.title=name;button.setAttribute('aria-pressed',String(selected));
  const icon=button.querySelector('span');if(icon)icon.textContent=kind==='shape'?'◇':'T';
  const text=[...button.childNodes].find(node=>node.nodeType===Node.TEXT_NODE);if(text)text.nodeValue=` ${name}`;else button.append(document.createTextNode(` ${name}`));
  const visible=row.querySelector('[data-design-toggle="visible"]'),locked=row.querySelector('[data-design-toggle="locked"]');
  visible.textContent=item.visible===false?'○':'●';visible.setAttribute('aria-label',`${name} ${item.visible===false?'표시':'숨기기'}`);
  locked.textContent=item.locked?'🔒':'◇';locked.setAttribute('aria-label',`${name} ${item.locked?'잠금 해제':'잠금'}`);
 }
}
function designPanels(){
 const list=$('#designerLayers');if(!list||!current())return;
 const row=(kind,o)=>{const selected=kind==='shape'?ve.selected.has(o.id):designer.labels.has(o.id);const name=kind==='shape'?o.name:o.name||o.text;return `<div class="design-layer ${selected?'selected':''}" draggable="true" data-design-row="${o.id}" data-kind="${kind}"><button data-design-select="${o.id}" data-kind="${kind}" title="${esc(name)}" aria-pressed="${selected}"><span>${kind==='shape'?'◇':'T'}</span> ${esc(name)}</button><button data-design-toggle="visible" data-id="${o.id}" data-kind="${kind}" aria-label="${esc(name)} ${o.visible===false?'표시':'숨기기'}" title="표시/숨김">${o.visible===false?'○':'●'}</button><button data-design-toggle="locked" data-id="${o.id}" data-kind="${kind}" aria-label="${esc(name)} ${o.locked?'잠금 해제':'잠금'}" title="잠금/해제">${o.locked?'🔒':'◇'}</button></div>`};
 if(!list.querySelector('[data-layer-list="label"]'))list.innerHTML=`<h4 data-layer-heading="label">글씨 <span></span></h4><div class="design-layer-list" data-layer-list="label"></div><h4 data-layer-heading="shape">그림 <span></span></h4><div class="design-layer-list" data-layer-list="shape"></div><p class="hint">위쪽일수록 앞에 표시됩니다. 같은 영역 안에서 끌어 순서를 바꿉니다. 글씨는 항상 그림 위에 유지됩니다.</p>`;
 designSyncLayerGroup(list,'label',current().image_labels);designSyncLayerGroup(list,'shape',vobjects());
 for(const [act,enabled] of [['undo',designer.history.getUndoStackSize()],['redo',designer.history.getRedoStackSize()]])document.querySelectorAll(`[data-vector-action=${act}],[data-design-action=${act}]`).forEach(b=>b.disabled=!enabled);
 const items=designItems();$('#designerSelection').textContent=items.length?`${items.length}개 선택`:'선택한 객체 없음';
 document.querySelectorAll('[data-design-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.designTool===designer.tool)));
 const label=chosen();if(label?.locked)$('#labelProperties')?.querySelectorAll('input,select,textarea,[data-layer-action]').forEach(el=>el.disabled=true);
 designObjectToolbar();
}
const designButtonIcons={all:'▣',copy:'▱',paste:'📋',duplicate:'⧉',delete:'🗑',front:'⤒',back:'⤓',group:'▦',ungroup:'▧',visible:'◉',lock:'🔒',flipx:'↔',flipy:'↕',left:'⇤',center:'↔',right:'⇥',top:'⤒',middle:'↕',bottom:'⤓','distribute-x':'↔','distribute-y':'↕'};
function designObjectToolbar(){
 const top=$('.designer-top');if(!top)return;
 let toolbar=$('#designerObjectToolbar');
 if(!toolbar){
  toolbar=document.createElement('div');toolbar.id='designerObjectToolbar';toolbar.className='designer-object-toolbar';toolbar.setAttribute('role','toolbar');toolbar.setAttribute('aria-label','선택 객체 편집');
  toolbar.innerHTML='<div id="designerEditActions" class="object-action-group" aria-label="복사와 삭제"></div><div id="designerArrangeActions" class="object-action-group" aria-label="순서와 묶음"></div><div id="designerRotateActions" class="object-action-group" aria-label="회전"></div><details class="object-align-menu"><summary>▤ 정렬·간격</summary><div id="designerAlignActions"></div></details>';
  top.append(toolbar);
  const selection=$('.design-selection-actions');if(selection){$('#designerEditActions').append(...selection.children);selection.remove()}
  const align=$('.designer-inspector .design-alignment');if(align){const section=align.closest('details');$('#designerAlignActions').append(align);section.remove()}
 }
 // Inspector fields are rebuilt on each selection; move their controls intact.
 const vector=$('#vectorProperties .vector-properties');
 const arrangement=$('#designerArrangeActions');
 if(vector&&!vector.dataset.toolbarMoved){
  vector.dataset.toolbarMoved="true";arrangement.replaceChildren();
  for(const button of vector.querySelectorAll('[data-vector-action]')){
   if(['duplicate','delete'].includes(button.dataset.vectorAction))button.remove();else arrangement.append(button);
  }
  vector.querySelectorAll('[data-valign]').forEach(button=>button.remove());
 }else if(!vector)arrangement.replaceChildren();
 $('#labelProperties')?.querySelectorAll('[data-layer-action="duplicate"],[data-layer-action="remove"]').forEach(button=>button.remove());
 const rotation=$('#rotateStepButtons');if(rotation&&rotation.parentElement!==$('#designerRotateActions')){$('#designerRotateActions').replaceChildren(rotation)}
 if(!vselected().length)$('#designerRotateActions').replaceChildren();
 for(const button of toolbar.querySelectorAll('button')){
  const key=button.dataset.designAction||button.dataset.vectorAction||button.dataset.designAlign;
  if(!button.dataset.iconReady){const text=button.textContent.trim();button.title=button.title||text;button.setAttribute('aria-label',button.title);if(key){const icon=document.createElement('span');icon.className='object-action-icon';icon.setAttribute('aria-hidden','true');icon.textContent=designButtonIcons[key]||'◇';button.prepend(icon)}button.dataset.iconReady='true'}
 }
 const items=designItems(),busy=state.job?.status==='running',locked=items.some(i=>i.o.locked);
 for(const button of toolbar.querySelectorAll('[data-design-action]')){const a=button.dataset.designAction;button.disabled=busy||(a==='all'? !vobjects().length&&!current().image_labels.length:a==='paste'? !designer.clipboard?.length||designer.clipboardKey!==designer.key:!items.length||(a!=='copy'&&locked))}
 for(const button of toolbar.querySelectorAll('[data-vector-action]')){const a=button.dataset.vectorAction;button.disabled=busy||!vselected().length||designer.labels.size>0||(!['lock','visible'].includes(a)&&locked)||(a==='group'&&vselected().length<2)||(a==='ungroup'&&vselected().length!==1)}
 toolbar.querySelectorAll('[data-rotate-step]').forEach(button=>button.disabled=busy||!vselected().length||locked||designer.labels.size>0);
 toolbar.querySelectorAll('[data-design-align]').forEach(button=>button.disabled=busy||!items.length||locked||(button.dataset.designAlign.startsWith('distribute')&&items.length<3));
}
const designBaseDraw=drawLayers;
drawLayers=function(){
 // Resize cached glyphs while dragging, then render the exact font once on release.
 const drag=designer.drag,o=drag?.type==='label-handle'&&drag.mode==='size'?chosen():null;
 const original=o&&glyphCache.get(glyphKey(drag.original)),key=o&&glyphKey(o),temporary=original&&!glyphCache.has(key);
 if(temporary){const ratio=o.size/drag.original.size;glyphCache.set(key,{...original,width:original.width*ratio,height:original.height*ratio})}
 designBaseDraw();if(temporary)glyphCache.delete(key);
 const svg=$('#layerCanvas');if(!svg)return;svg.querySelectorAll('[data-label]').forEach(el=>{const label=current().image_labels.find(item=>item.id===el.dataset.label);if(label?.visible===false)el.remove()});designOverlay();
};
function designOverlay(){
 const svg=$('#layerCanvas');if(!svg)return;const overlay=document.createElementNS(SVGNS,'g');overlay.id='designerOverlay';
 let html='';for(const o of current().image_labels.filter(o=>designer.labels.has(o.id)&&o.visible!==false)){
  const b=designLabelBox(o);html+=`<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="none" stroke="#365eef" stroke-width="1.5" pointer-events="none"/>`;
  if(designer.labels.size===1&&!ve.selected.size&&!o.locked)html+=`<rect data-design-handle="size" x="${b.x+b.w-6}" y="${b.y+b.h-6}" width="12" height="12" fill="white" stroke="#365eef" stroke-width="2"/><path d="M${b.x+b.w/2} ${b.y}v-24" stroke="#365eef" pointer-events="none"/><circle data-design-handle="rotation" cx="${b.x+b.w/2}" cy="${b.y-24}" r="6" fill="#365eef"/>`;
 }
 for(const g of designer.guides)html+=snapGuideMarkup(g);
 const d=designer.drag;if(d?.type==='marquee'){const b=d.rect;html+=`<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="#365eef16" stroke="#365eef" pointer-events="none"/>`}
 if(d?.type==='draw'&&d.markup)html+=`<g fill="none" stroke="#365eef" stroke-width="2" pointer-events="none">${d.markup}</g>`;
 overlay.innerHTML=html;svg.append(overlay);
}
function designPoint(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform($('#layerCanvas').getScreenCTM().inverse())}
function designSnap(dx,dy,b,items){
 designer.guides=[];if(!designer.snap||!b)return [dx,dy];
 const ids=new Set(items.map(i=>i.o.id));const boxes=[{x:0,y:0,w:1000,h:640},...vobjects().filter(o=>!ids.has(o.id)&&o.visible).map(o=>vbox(o)),...current().image_labels.filter(o=>!ids.has(o.id)&&o.visible!==false).map(designLabelBox)].filter(Boolean);
 for(const axis of ['x','y']){const size=axis==='x'?'w':'h',delta=axis==='x'?dx:dy;let best=6,adjust=0,target=null;
  for(const box of boxes)for(const f of [0,.5,1])for(const t of [0,.5,1]){const value=box[axis]+box[size]*t,diff=value-(b[axis]+b[size]*f+delta);if(Math.abs(diff)<best){best=Math.abs(diff);adjust=diff;target=value}}
  if(target!==null){if(axis==='x')dx+=adjust;else dy+=adjust;designer.guides.push({axis,value:target})}
 }return [dx,dy];
}
function designToolMarkup(tool,a,b,points,shift){if(shift&&tool==='line')b=SvgEditCore.snapToAngle(a.x,a.y,b.x,b.y);let w=b.x-a.x,h=b.y-a.y;if(shift&&['rect','ellipse'].includes(tool)){const size=Math.max(Math.abs(w),Math.abs(h));w=Math.sign(w||1)*size;h=Math.sign(h||1)*size}const x=Math.min(a.x,a.x+w),y=Math.min(a.y,a.y+h);if(tool==='rect')return `<rect x="${x}" y="${y}" width="${Math.abs(w)}" height="${Math.abs(h)}"/>`;if(tool==='ellipse')return `<ellipse cx="${x+Math.abs(w)/2}" cy="${y+Math.abs(h)/2}" rx="${Math.abs(w)/2}" ry="${Math.abs(h)/2}"/>`;if(tool==='pen')return `<polyline points="${points.map(p=>`${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}" stroke-linecap="round" stroke-linejoin="round"/>`;return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`}
const designBaseInit=initVectorEditor;
initVectorEditor=function(){
 designBaseInit();const svg=$('#layerCanvas');if(!svg)return;
 const key=typeof uxImageToolKey==='function'?uxImageToolKey():state.exam.id+current().id+(current().image?.file||'')+(current().image?.sha256||'');if(designer.key!==key){designer.key=key;designer.before=null;designer.drag=null;designer.space=false;if(typeof uxRestoreImageToolState!=='function'){designer.history.resetUndoStack();designer.labels.clear()}}
 designer.labels=new Set([...designer.labels].filter(id=>current().image_labels.some(o=>o.id===id)));
 selectedLabel=designer.labels.size===1?[...designer.labels][0]:null;
 designLayout();drawLayers();renderLabelProperties();designPanels();
 const down=svg.onpointerdown,move=svg.onpointermove,up=svg.onpointerup,cancel=svg.onpointercancel;
 svg.onpointerdown=e=>{
  if(state.job?.status==='running')return;
  const wrap=$('.layer-canvas-wrap');
  if(designer.tool==='hand'||designer.space||e.button===1){designer.drag={type:'pan',clientX:e.clientX,clientY:e.clientY,left:wrap.scrollLeft,top:wrap.scrollTop};svg.setPointerCapture(e.pointerId);e.preventDefault();return}
  if(e.button!==0)return;
  const p=designPoint(e),handle=e.target.closest('[data-design-handle]');
  if(handle&&chosen()&&!chosen().locked){designBegin();designer.drag={type:'label-handle',mode:handle.dataset.designHandle,start:p,original:structuredClone(chosen()),box:designLabelBox(chosen())};svg.setPointerCapture(e.pointerId);e.preventDefault();return}
  if(['line','rect','ellipse','pen'].includes(designer.tool)){
   if(!scene()){toast('먼저 그림을 편집 객체로 변환하세요.');return}if(vobjects().length>=500){toast('도형은 최대 500개입니다.');return}
   designBegin();designer.drag={type:'draw',tool:designer.tool,start:p,points:[p],markup:''};svg.setPointerCapture(e.pointerId);svg.focus();e.preventDefault();return;
  }
  if(e.target.closest('[data-vhandle],[data-vnode]')){designer.labels.clear();down(e);if(ve.drag)ve.drag.start=designPoint(e);return}
  const shape=e.target.closest('[data-vector]'),label=e.target.closest('[data-label]');
  if(shape||label){const kind=shape?'shape':'label',id=(shape||label).dataset[shape?'vector':'label'],set=shape?ve.selected:designer.labels;
   if(e.shiftKey||!set.has(id))designSelect(kind,id,e.shiftKey);
   const items=designItems();designRefresh();
   if(items.length&&!items.some(i=>i.o.locked||i.o.visible===false)){designBegin();designer.drag={type:'move',start:p,items:items.map(i=>({kind:i.kind,o:structuredClone(i.o)})),box:designUnion(items)}}
  }else{if(!e.shiftKey)designClear();designer.drag={type:'marquee',start:p,rect:{x:p.x,y:p.y,w:0,h:0},shapes:[...ve.selected],labels:[...designer.labels]}}
  svg.setPointerCapture(e.pointerId);svg.focus();e.preventDefault();drawLayers();
 };
 svg.onpointermove=e=>{
  const d=designer.drag;if(!d){if(!snapHandleMove(e))move(e);return}
  if(d.type==='pan'){const wrap=$('.layer-canvas-wrap');wrap.scrollLeft=d.left-(e.clientX-d.clientX);wrap.scrollTop=d.top-(e.clientY-d.clientY);return}
  const p=designPoint(e);let dx=p.x-d.start.x,dy=p.y-d.start.y;
  if(d.type==='move'){
   if(e.shiftKey){if(Math.abs(dx)>Math.abs(dy))dy=0;else dx=0}
   snapClear();if(ve.snap&&!e.altKey){dx=Math.round(dx/10)*10;dy=Math.round(dy/10)*10}else if(!e.altKey)[dx,dy]=designSnap(dx,dy,d.box,d.items,e.shiftKey?(Math.abs(dx)>Math.abs(dy)?'x':'y'):null);
   for(const item of d.items){const target=(item.kind==='shape'?vobjects():current().image_labels).find(o=>o.id===item.o.id);Object.assign(target,structuredClone(item.o));designMove({kind:item.kind,o:target},dx,dy)}vdirty();
  }else if(d.type==='marquee'){
   d.rect={x:Math.min(p.x,d.start.x),y:Math.min(p.y,d.start.y),w:Math.abs(dx),h:Math.abs(dy)};const r={x:d.rect.x,y:d.rect.y,width:d.rect.w,height:d.rect.h};ve.selected=new Set(d.shapes);designer.labels=new Set(d.labels);
   for(const item of [...vobjects().map(o=>({kind:'shape',o})),...current().image_labels.map(o=>({kind:'label',o}))]){if(item.o.visible===false||item.o.locked)continue;const b=designBox(item);if(b&&SvgEditCore.rectsIntersect(r,{x:b.x,y:b.y,width:Math.max(1,b.w),height:Math.max(1,b.h)}))(item.kind==='shape'?ve.selected:designer.labels).add(item.o.id)}
  }else if(d.type==='draw'){
   if(d.points.length<1000)d.points.push(p);d.markup=designToolMarkup(d.tool,d.start,p,d.points,e.shiftKey);
  }else if(d.type==='label-handle'){
   const o=chosen(),b=d.box,cx=b.x+b.w/2,cy=b.y+b.h/2;
   if(d.mode==='size'){o.size=Math.max(8,Math.min(120,Math.round(d.original.size*Math.hypot(p.x-b.x,p.y-b.y)/Math.max(1,Math.hypot(d.start.x-b.x,d.start.y-b.y)))))}
   else{let angle=d.original.rotation+(Math.atan2(p.y-cy,p.x-cx)-Math.atan2(d.start.y-cy,d.start.x-cx))*180/Math.PI;angle=snapAngleValue(angle,!e.altKey&&(snapOptions.angle||e.shiftKey));snapNote(`글씨 회전 ${Math.round(angle*10)/10}°`);o.rotation=((angle+540)%360)-180}markLabelDirty();
  }drawLayers();
 };
 svg.onpointerup=e=>{
  const d=designer.drag;if(d?.type==='draw'&&d.markup){const id=vid();scene().objects.push({id,name:{line:'선',rect:'사각형',ellipse:'타원',pen:'자유 곡선'}[d.tool],svg:`<g fill="none" stroke="black" stroke-width="2">${d.markup}</g>`,matrix:[1,0,0,1,0,0],visible:true,locked:false});designSelect('shape',id);vdirty()}
  designer.drag=null;snapClear();up(e);designCommit();designRefresh();
 };
 svg.onpointercancel=e=>{const snapshot=designer.before;designer.drag=null;snapClear();designer.before=null;cancel(e);if(snapshot){const restored=JSON.parse(snapshot);current().image_scene=restored.scene;current().image_labels=restored.labels;current().labels_initialized=restored.initialized}designRefresh()};
 svg.onkeydown=e=>{
  if(state.job?.status==='running')return;const mod=e.ctrlKey||e.metaKey,k=e.key.toLowerCase();
  if(e.code==='Space'){designer.space=true;e.preventDefault();return}
  if(mod&&['z','y','a','c','v','d'].includes(k)){e.preventDefault();if(k==='z'||k==='y')designHistory(k==='y'||e.shiftKey?'redo':'undo');else designAction({a:'all',c:'copy',v:'paste',d:'duplicate'}[k]);return}
  if(['Delete','Backspace'].includes(e.key)){e.preventDefault();designAction('delete');return}
  const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(delta){e.preventDefault();const items=designItems();if(items.some(i=>i.o.locked))return;designBegin();for(const i of items)designMove(i,delta[0]*(e.shiftKey?10:1),delta[1]*(e.shiftKey?10:1));if(items.length)vdirty();designCommit('nudge');designRefresh();return}
  if(e.key==='Escape'){designer.tool='select';designClear();designRefresh()}else if(!mod&&['v','h','l','r','e','p'].includes(k)){designer.tool={v:'select',h:'hand',l:'line',r:'rect',e:'ellipse',p:'pen'}[k];designPanels()}
 };
 svg.onkeyup=e=>{if(e.code==='Space')designer.space=false};svg.onblur=()=>designer.space=false;
 svg.addEventListener('wheel',e=>{if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();designZoom(ve.zoom+(e.deltaY<0?10:-10),e)},{passive:false});
 let dragged=null;$('#designerLayers').ondragstart=e=>{const row=e.target.closest('[data-design-row]');if(row){dragged={id:row.dataset.designRow,kind:row.dataset.kind};e.dataTransfer.setData('text/plain',dragged.id)}};
 $('#designerLayers').ondragover=e=>{if(e.target.closest('[data-design-row]')?.dataset.kind===dragged?.kind)e.preventDefault()};
 $('#designerLayers').ondrop=e=>{e.preventDefault();if(state.job?.status==='running')return;const row=e.target.closest('[data-design-row]');if(!row||row.dataset.kind!==dragged?.kind||row.dataset.designRow===dragged.id)return;const all=dragged.kind==='shape'?vobjects():current().image_labels,item=all.find(o=>o.id===dragged.id);if(item.locked){toast('잠금을 해제한 뒤 순서를 바꾸세요.');return}designBegin();const target=all.findIndex(o=>o.id===row.dataset.designRow);all.splice(all.indexOf(item),1);all.splice(target,0,item);vdirty();designCommit();designRefresh();dragged=null};
};
function designZoom(value,event){const wrap=$('.layer-canvas-wrap'),svg=$('#layerCanvas'),rect=wrap.getBoundingClientRect(),x=event?event.clientX-rect.left:wrap.clientWidth/2,y=event?event.clientY-rect.top:wrap.clientHeight/2,old=ve.zoom;ve.zoom=Math.max(25,Math.min(400,Math.round(value)));const left=(wrap.scrollLeft+x)*ve.zoom/old-x,top=(wrap.scrollTop+y)*ve.zoom/old-y;vzoom();wrap.scrollLeft=left;wrap.scrollTop=top;$('#designerZoom').textContent=ve.zoom+'%';const select=$('#vectorZoom');if(select)select.value=String(ve.zoom)}
const designViewportObserver=new ResizeObserver(()=>{if(ve.expanded)vzoom()});
function designLayout(){
 const wrap=$('.layer-canvas-wrap');if(!wrap||$('#designerShell'))return;
 const shell=document.createElement('div');shell.id='designerShell';shell.className='designer-shell';
 shell.innerHTML=`<div class="designer-top"><strong>자료 디자인</strong><span id="designerSelection"></span><div class="designer-history"><button data-design-action="undo" title="Ctrl+Z">↶ 실행 취소</button><button data-design-action="redo" title="Ctrl+Shift+Z">↷ 다시 실행</button></div></div><aside class="designer-layers"><h3>레이어</h3><div id="designerLayers"></div></aside><div class="designer-center"><div class="designer-tools" role="toolbar" aria-label="그림 도구">${[['select','↖ 선택','V'],['hand','✋ 이동','H'],['line','╱ 선','L'],['rect','□ 사각형','R'],['ellipse','○ 타원','E'],['pen','⌁ 펜','P']].map(([tool,label,key])=>`<button data-design-tool="${tool}" title="${label} (${key})" aria-pressed="false">${label}</button>`).join('')}</div><div class="designer-ruler" aria-hidden="true">${Array.from({length:11},(_,i)=>`<span>${i*100}</span>`).join('')}</div><div id="designerViewport"></div><div class="designer-status"><span>1000 × 640 · Shift 비율/각도 고정</span><label><input id="designerSnap" type="checkbox" ${designer.snap?'checked':''}> 스마트 정렬</label><button data-design-zoom="minus" aria-label="축소">−</button><button id="designerZoom" data-design-zoom="fit" title="화면에 맞춤">${ve.zoom}%</button><button data-design-zoom="plus" aria-label="확대">＋</button></div></div><aside class="designer-inspector"><h3>속성</h3><div class="design-selection-actions">${[['all','전체 선택'],['copy','복사'],['paste','붙여넣기'],['duplicate','복제'],['delete','삭제']].map(([a,l])=>`<button data-design-action="${a}">${l}</button>`).join('')}</div><details open><summary>정렬 · 간격</summary><div class="design-alignment">${[['left','왼쪽'],['center','가로 중앙'],['right','오른쪽'],['top','위'],['middle','세로 중앙'],['bottom','아래'],['distribute-x','가로 간격'],['distribute-y','세로 간격']].map(([a,l])=>`<button data-design-align="${a}">${l}</button>`).join('')}</div></details><label id="designerLabelName" hidden>레이어 이름<input id="designerName" maxlength="80"></label><div id="designerInspectorBody"></div></aside>`;
 wrap.before(shell);$('.designer-tools').append(...document.querySelectorAll('.layer-toolbar [data-add-label]'));$('#designerViewport').append(wrap);$('#designerInspectorBody').append($('#vectorProperties'),$('#labelProperties'));
 const panel=shell.closest('section.panel');panel.classList.add('design-document');
 // Keep the artboard in view; infrequent source/advanced controls stay nearby.
 const expand=panel.querySelector('[data-vector-action=expand]');if(expand)$('.designer-history').prepend(expand);
 const preparation=document.createElement('details');preparation.id='designerPreparation';preparation.className='designer-preparation';preparation.open=!scene()||!!designer.preparation;
 const summary=document.createElement('summary');summary.textContent='배경 생성·가져오기 / 기본 도형·격자 설정';summary.onclick=()=>{designer.preparation=!preparation.open};preparation.append(summary);
 const preceding=[];for(let n=panel.querySelector('.panel-body').firstChild;n&&n!==shell;n=n.nextSibling)preceding.push(n);
 for(const n of preceding)preparation.append(n);shell.before(preparation);
 const hint=wrap.nextElementSibling;if(hint?.classList.contains('hint'))hint.remove();
 designViewportObserver.disconnect();designViewportObserver.observe($('#designerViewport'));vzoom();
}
async function designAction(act){
 if(state.job?.status==='running')return;
 if(act==='undo'||act==='redo'){designHistory(act);return}
 if(act==='all'){ve.selected=new Set(vobjects().filter(o=>o.visible&&!o.locked).map(o=>o.id));designer.labels=new Set(current().image_labels.filter(o=>o.visible!==false&&!o.locked).map(o=>o.id));designRefresh();return}
 const items=designItems();if(act==='copy'){designer.clipboard=structuredClone(items);designer.clipboardKey=designer.key;designPanels();toast('선택 객체를 편집기 안에 복사했습니다.');return}
 if(act!=='paste'&&items.some(i=>i.o.locked)){toast('잠금 객체를 해제한 뒤 편집하세요.');return}
 if(act==='paste'&&designer.clipboardKey!==designer.key){toast('같은 자료 그림 안에서 복사·붙여넣기 할 수 있습니다.');return}const copies=act==='paste'?designer.clipboard:items;if(['paste','duplicate'].includes(act)&&(!copies?.length||!current().image))return;
 if(['paste','duplicate'].includes(act)&&((!scene()&&copies.some(i=>i.kind==='shape'))||vobjects().length+copies.filter(i=>i.kind==='shape').length>500||current().image_labels.length+copies.filter(i=>i.kind==='label').length>80)){toast('객체 변환 여부와 도형 500개·글씨 80개 제한을 확인하세요.');return}
 designBegin();
 if(act==='delete'){current().image_scene&&(current().image_scene.objects=vobjects().filter(o=>!ve.selected.has(o.id)));current().image_labels=current().image_labels.filter(o=>!designer.labels.has(o.id));designClear()}
 if(['paste','duplicate'].includes(act)){designClear();for(const source of copies){const item=structuredClone(source);item.o.id=vid();item.o.locked=false;designMove(item,20,20);(item.kind==='shape'?vobjects():current().image_labels).push(item.o);(item.kind==='shape'?ve.selected:designer.labels).add(item.o.id)}current().labels_initialized=true}
 if(items.length||copies?.length)vdirty();designCommit();designRefresh();
}
function designAlign(mode){
 const items=designItems();if(state.job?.status==='running'||items.some(i=>i.o.locked)){toast('잠금 또는 생성 작업이 끝난 뒤 편집하세요.');return}if(!items.length)return;
 const b=items.length===1?{x:0,y:0,w:1000,h:640}:designUnion();if(!b)return;
 if(mode.startsWith('distribute')&&items.length<3){toast('간격 정렬은 3개 이상 선택하세요.');return}
 designBegin();
 if(mode.startsWith('distribute')){const axis=mode.endsWith('x')?'x':'y',size=axis==='x'?'w':'h',sorted=items.map(i=>({i,b:designBox(i)})).filter(x=>x.b).sort((a,z)=>a.b[axis]-z.b[axis]);if(sorted.length>=3){const first=sorted[0].b,last=sorted.at(-1).b,gap=(last[axis]+last[size]-first[axis]-sorted.reduce((s,x)=>s+x.b[size],0))/(sorted.length-1);let at=first[axis];for(const {i,b:r} of sorted){designMove(i,axis==='x'?at-r.x:0,axis==='y'?at-r.y:0);at+=r[size]+gap}}}
 else for(const i of items){const r=designBox(i);if(!r)continue;designMove(i,{left:b.x-r.x,center:b.x+b.w/2-r.x-r.w/2,right:b.x+b.w-r.x-r.w}[mode]||0,{top:b.y-r.y,middle:b.y+b.h/2-r.y-r.h/2,bottom:b.y+b.h-r.y-r.h}[mode]||0)}
 vdirty();designCommit();designRefresh();
}
// Capture text edits before the legacy handlers run; group consecutive typing.
for(const type of ['input','click','change'])document.addEventListener(type,e=>{
 if(!$('#layerCanvas')||state.job?.status==='running')return;
 const el=e.target,edit=el.closest('[data-vprop],[data-vector-add],[data-valign],[data-label-prop],[data-add-label],[data-layer-action="remove"],[data-layer-action="duplicate"],[data-layer-action="empty"]');
 if(edit){if(chosen()?.locked&&edit.matches('[data-label-prop],[data-layer-action="remove"],[data-layer-action="duplicate"]')){e.stopImmediatePropagation();e.preventDefault();return}designBegin();e.designEdit=edit}
 if(el.closest('[data-select-label],[data-vselect]'))e.designSelection=true;
},true);
for(const type of ['input','click','change'])document.addEventListener(type,e=>{
 if(e.designEdit){if(e.designEdit.dataset.addLabel||e.designEdit.dataset.layerAction)designer.labels=new Set(selectedLabel?[selectedLabel]:[]);designCommit(e.designEdit.dataset.labelProp||'');designPanels()}
 if(e.designSelection){designer.labels=new Set(selectedLabel?[selectedLabel]:[]);designRefresh()}
});
document.addEventListener('click',e=>{
 const button=e.target.closest('[data-design-tool],[data-design-select],[data-design-toggle],[data-design-action],[data-design-align],[data-design-zoom]');if(!button)return;
 action(async()=>{if(state.job?.status==='running')return;
  if(button.dataset.designTool){designer.tool=button.dataset.designTool;designPanels();return}
  if(button.dataset.designSelect){designSelect(button.dataset.kind,button.dataset.designSelect,e.shiftKey);designRefresh();return}
  if(button.dataset.designAction){await designAction(button.dataset.designAction);return}
  if(button.dataset.designAlign){designAlign(button.dataset.designAlign);return}
  if(button.dataset.designZoom){designZoom(button.dataset.designZoom==='fit'?100:ve.zoom+(button.dataset.designZoom==='plus'?25:-25));return}
  const o=(button.dataset.kind==='shape'?vobjects():current().image_labels).find(o=>o.id===button.dataset.id);if(o){designBegin();const key=button.dataset.designToggle;o[key]=key==='visible'?o.visible===false:!o.locked;vdirty();designCommit();designRefresh()}
 });
});
document.addEventListener('change',e=>{if(e.target.id==='designerSnap')designer.snap=e.target.checked;if(e.target.id==='designerName'&&chosen()&&!chosen().locked&&state.job?.status!=='running'){designBegin();chosen().name=e.target.value.slice(0,80);markLabelDirty();designCommit();designPanels()}});
const designBaseProperties=renderLabelProperties;
renderLabelProperties=function(rebuild=true){designBaseProperties(rebuild);const row=$('#designerLabelName'),o=chosen();if(row){row.hidden=!o;if(o){$('#designerName').value=o.name||'';$('#designerName').disabled=!!o.locked}}if(o?.locked)$('#labelProperties')?.querySelectorAll('input,textarea,select,button[data-layer-action]').forEach(el=>el.disabled=true)};
const designBaseVectorProperties=vproperties;
vproperties=function(){designBaseVectorProperties();designPanels()};

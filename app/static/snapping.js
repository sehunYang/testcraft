'use strict';
// Snap only the preview transform. Guides are never part of the exported SVG.
const snapOptions={position:true,size:true,angle:true};
function snapTolerance(){const m=$('#layerCanvas')?.getScreenCTM();return 7/Math.max(.05,m?Math.hypot(m.a,m.b):1)}
function snapReferences(ids=new Set(),canvas=false){
 const items=[...vobjects().filter(o=>!ids.has(o.id)&&o.visible!==false).map(o=>({box:vbox(o),name:o.name})),...(current()?.image_labels||[]).filter(o=>!ids.has(o.id)&&o.visible!==false).map(o=>({box:designLabelBox(o),name:o.name||o.text}))].filter(x=>x.box);
 if(canvas)items.push({box:{x:0,y:0,w:1000,h:640},name:'캔버스'});return items;
}
function snapAngleValue(angle,enabled){return enabled?Math.round(angle/15)*15:angle}
function snapAngleOf(o){return Math.atan2(o.matrix[1],o.matrix[0])*180/Math.PI}
function snapClear(){designer.guides=[];designer.snapNote='';const status=$('#snapFeedback');if(status)status.textContent='Alt: 스냅 잠시 해제'}
function snapNote(text){designer.snapNote=text;const status=$('#snapFeedback');if(status)status.textContent=text||'Alt: 스냅 잠시 해제'}
function snapMove(dx,dy,b,refs,tolerance,axisLock){
 const guides=[];
 for(const axis of ['x','y']){
  if(axisLock&&axis!==axisLock)continue;
  const size=axis==='x'?'w':'h',delta=axis==='x'?dx:dy;let best=null;
  for(const ref of refs)for(const from of [0,.5,1])for(const to of [0,.5,1]){
   const value=ref.box[axis]+ref.box[size]*to,diff=value-(b[axis]+b[size]*from+delta);
   if(Math.abs(diff)<=tolerance&&(!best||Math.abs(diff)<Math.abs(best.diff)))best={diff,value,ref};
  }
  if(best){if(axis==='x')dx+=best.diff;else dy+=best.diff;guides.push({axis,value:best.value,label:`${best.ref.name} ${axis==='x'?'가로':'세로'} 정렬`})}
 }return {dx,dy,guides};
}
designSnap=function(dx,dy,b,items,axisLock){
 snapClear();if(!designer.snap||!snapOptions.position||!b)return [dx,dy];
 const result=snapMove(dx,dy,b,snapReferences(new Set(items.map(i=>i.o.id)),true),snapTolerance(),axisLock);
 designer.guides=result.guides;snapNote(result.guides.map(g=>g.label).join(' · '));return [result.dx,result.dy];
};
// Opposite handle stays fixed, including west/north handles and aspect-locked edits.
function snapResize(b,handle,sx,sy,refs,tolerance,{position=true,size=true,aspect=false}={}){
 const ox=handle.includes('w')?b.x+b.w:b.x,oy=handle.includes('n')?b.y+b.h:b.y;
 const proposals={x:[],y:[]};
 for(const axis of ['x','y']){
  const dim=axis==='x'?'w':'h',active=axis==='x'?/[ew]/.test(handle):/[ns]/.test(handle);
  if(!active||b[dim]<.01)continue;
  const sign=(axis==='x'?handle.includes('w'):handle.includes('n'))?-1:1,anchor=axis==='x'?ox:oy,scale=axis==='x'?sx:sy;
  const edge=anchor+sign*b[dim]*scale;
  for(const ref of refs){
   const add=(factor,kind,value,error)=>{if(factor>=.02&&error<=tolerance)proposals[axis].push({axis,factor,kind,value,error,ref})};
   if(size&&ref.name!=='캔버스'&&ref.box[dim]>.01)add(ref.box[dim]/b[dim],'size',ref.box[dim],Math.abs(ref.box[dim]-b[dim]*scale));
   if(position)for(const f of [0,.5,1]){const value=ref.box[axis]+ref.box[dim]*f;add((value-anchor)/(sign*b[dim]),'position',value,Math.abs(value-edge))}
  }
  proposals[axis].sort((a,z)=>a.error-z.error||(a.kind==='size'?-1:1));
 }
 let chosen=[];
 if(aspect){const all=[...proposals.x,...proposals.y].sort((a,z)=>a.error-z.error);if(all.length){chosen=[all[0]];sx=sy=all[0].factor}}
 else{if(proposals.x.length){sx=proposals.x[0].factor;chosen.push(proposals.x[0])}if(proposals.y.length){sy=proposals.y[0].factor;chosen.push(proposals.y[0])}}
 const box={x:ox+(b.x-ox)*sx,y:oy+(b.y-oy)*sy,w:b.w*sx,h:b.h*sy};
 return {sx,sy,ox,oy,box,guides:chosen.map(c=>c.kind==='size'?{kind:'size',axis:c.axis,box,reference:c.ref.box,value:c.value,label:`${c.axis==='x'?'너비':'높이'} ${Math.round(c.value*100)/100} 일치 · ${c.ref.name}`}:{axis:c.axis,value:c.value,label:`${c.ref.name} 가장자리 정렬`})};
}
function snapHandleMove(e){
 const d=ve.drag;if(!d||!['rotate','nw','n','ne','e','se','s','sw','w'].includes(d.type))return false;
 if(e.pointerId!==d.pointer)return true;
 snapClear();const raw=designPoint(e),p=ve.snap&&!e.altKey&&d.type!=='rotate'?{x:Math.round(raw.x/10)*10,y:Math.round(raw.y/10)*10}:raw;
 const b=d.box,dx=p.x-d.start.x,dy=p.y-d.start.y;let m;
 if(d.type==='rotate'){
  const cx=b.x+b.w/2,cy=b.y+b.h/2,base=d.items.length===1?snapAngleOf(d.items[0]):0;
  let delta=(Math.atan2(p.y-cy,p.x-cx)-Math.atan2(d.start.y-cy,d.start.x-cx))*180/Math.PI;
  const enabled=!e.altKey&&(snapOptions.angle||e.shiftKey),angle=snapAngleValue(base+delta,enabled);delta=angle-base;
  m=vcenterTransform(b,new DOMMatrix().rotate(delta));
  designer.guides=[{kind:'angle',cx,cy,angle,r:Math.max(35,Math.min(90,Math.max(b.w,b.h)/2))}];
  snapNote(`${d.items.length===1?'회전':'묶음 회전'} ${Math.round(angle*10)/10}°${enabled?' · 15° 스냅':''}`);
 }else{
  const h=d.type,aspect=ve.aspect||e.shiftKey;
  let sx=Math.max(.02,h.includes('e')?1+dx/(b.w||1):h.includes('w')?1-dx/(b.w||1):1),sy=Math.max(.02,h.includes('s')?1+dy/(b.h||1):h.includes('n')?1-dy/(b.h||1):1);
  if(aspect){if(h==='n'||h==='s')sx=sy;else sy=sx}
  const enabled=designer.snap&&!e.altKey;
  const result=snapResize(b,h,sx,sy,snapReferences(new Set(d.items.map(o=>o.id)),true),snapTolerance(),{position:enabled&&snapOptions.position,size:enabled&&snapOptions.size,aspect});
  m=new DOMMatrix().translate(result.ox,result.oy).scale(result.sx,result.sy).translate(-result.ox,-result.oy);
  designer.guides=result.guides;snapNote(result.guides.map(g=>g.label).join(' · ')||`너비 ${result.box.w.toFixed(1)} · 높이 ${result.box.h.toFixed(1)}`);
 }
 for(const original of d.items){const o=vobjects().find(o=>o.id===original.id);if(o)o.matrix=va(m.multiply(vm(original.matrix)))}
 vdirty();drawLayers();return true;
}
function snapGuideMarkup(g){
 const stroke='stroke="#d33789" stroke-width="1.5" vector-effect="non-scaling-stroke"';
 if(g.kind==='angle'){const a=g.angle*Math.PI/180,x=g.cx+g.r*Math.cos(a),y=g.cy+g.r*Math.sin(a);return `<g data-snap-guide="angle" pointer-events="none"><circle cx="${g.cx}" cy="${g.cy}" r="${g.r}" fill="none" ${stroke} stroke-dasharray="3 5"/><path d="M${g.cx} ${g.cy}H${g.cx+g.r}M${g.cx} ${g.cy}L${x} ${y}" ${stroke}/><text x="${g.cx+12}" y="${g.cy-12}" fill="#a32163" font-size="15">${Math.round(g.angle*10)/10}°</text></g>`}
 if(g.kind==='size'){
  const dimension=b=>g.axis==='x'?`M${b.x} ${b.y-12}h${b.w}M${b.x} ${b.y-17}v10M${b.x+b.w} ${b.y-17}v10`:`M${b.x+b.w+12} ${b.y}v${b.h}M${b.x+b.w+7} ${b.y}h10M${b.x+b.w+7} ${b.y+b.h}h10`;
  return `<g data-snap-guide="size" pointer-events="none"><path d="${dimension(g.box)}${dimension(g.reference)}" fill="none" ${stroke}/><text x="${g.box.x}" y="${g.box.y-20}" fill="#a32163" font-size="14">${g.axis==='x'?'W':'H'} = ${Math.round(g.value*100)/100}</text></g>`;
 }
 return `<path data-snap-guide="position" d="${g.axis==='x'?`M${g.value} 0V640`:`M0 ${g.value}H1000`}" ${stroke} stroke-dasharray="4 4" pointer-events="none"/>`;
}
const snapBaseLayout=designLayout;
designLayout=function(){snapBaseLayout();const status=$('.designer-status');if(!status||$('#snapFeedback'))return;
 const options=document.createElement('div');options.className='snap-options';options.innerHTML=`${[['angle','15° 회전'],['position','객체 위치'],['size','같은 너비·높이']].map(([key,title])=>`<label><input type="checkbox" data-snap-option="${key}" ${snapOptions[key]?'checked':''}>${title}</label>`).join('')}<span id="snapFeedback" role="status" aria-live="polite">Alt: 스냅 잠시 해제</span>`;status.before(options);
};
const snapBaseProperties=vproperties;
vproperties=function(){snapBaseProperties();const field=$('[data-vprop=rotation]');if(!field)return;field.step='15';if($('#rotateStepButtons'))return;
 const buttons=document.createElement('div');buttons.id='rotateStepButtons';buttons.className='full buttons-wrap';buttons.innerHTML='<button data-rotate-step="-15" title="반시계 방향으로 15도 회전">↶ −15°</button><button data-rotate-step="15" title="시계 방향으로 15도 회전">↷ ＋15°</button>';field.closest('label').after(buttons);designObjectToolbar();
};
document.addEventListener('change',e=>{if(e.target.dataset.snapOption){snapOptions[e.target.dataset.snapOption]=e.target.checked;snapClear();drawLayers()}if(e.target.id==='designerSnap'){snapClear();drawLayers()}});
document.addEventListener('click',e=>{const btn=e.target.closest('[data-rotate-step]');if(!btn||state.job?.status==='running')return;const items=vselected(),b=vunion();if(!b||items.some(o=>o.locked))return;designBegin();vtransform(items,vcenterTransform(b,new DOMMatrix().rotate(Number(btn.dataset.rotateStep))));vdirty();designCommit();designRefresh()});

'use strict';
// 앱 그래프 수치 입력 칸(2026-11-13). SVG 규칙 칸의 "도식: {JSON}" 가운데 그래프(chart)·함수 그래프(function)를
// 표처럼 고친다. 고친 명세는 그 칸에 다시 써서 기존 저장·승인 흐름(카드 재검토, 계획 확인)을 그대로 탄다.
const SPEC_PREFIX='도식:';
const specEd={writing:false,timer:0,request:0};
const SPEC_CHART_NAMES={bar:'막대그래프',line:'꺾은선그래프',pie:'원그래프',band:'띠그래프',scatter:'산점 그래프'};

function specParse(text){
 const t=String(text||'').trim();if(!t.startsWith(SPEC_PREFIX))return null;
 try{const spec=JSON.parse(t.slice(SPEC_PREFIX.length));return spec&&typeof spec==='object'&&!Array.isArray(spec)?spec:null}catch{return null}
}
// 고칠 수 있는 그래프 목록: 한 장이면 [ [], 명세 ], (가)(나)면 칸마다.
function specGraphs(spec){
 const ok=g=>g&&typeof g==='object'&&(g.type==='chart'||g.type==='function');
 if(spec?.type==='panels')return (spec.items||[]).map((g,i)=>[['items',i],g]).filter(([,g])=>ok(g));
 return ok(spec)?[[[],spec]]:[];
}
function specGet(obj,path){return path.reduce((o,k)=>o==null?undefined:o[k],obj)}
function specSet(obj,path,value){
 let o=obj;for(let i=0;i<path.length-1;i++){const k=path[i];if(o[k]==null||typeof o[k]!=='object')o[k]=typeof path[i+1]==='number'?[]:{};o=o[k]}
 const last=path[path.length-1];if(value===undefined){if(Array.isArray(o))o[last]=null;else delete o[last]}else o[last]=value;
}
function specNum(v){const t=String(v).trim().replace(/−/g,'-').replace(/,/g,'');if(!t)return null;const n=Number(t);return Number.isFinite(n)?n:NaN}
function specFmt(v){return v==null?'':String(v)}
// 입력 칸 글을 명세 값으로. undefined는 키를 지운다, NaN이 섞이면 잘못된 입력.
const SPEC_KINDS={
 text:v=>v,
 num:v=>{const n=specNum(v);return n===null?NaN:n},
 numnull:v=>specNum(v),
 opt:v=>{const n=specNum(v);return n===null?undefined:n},
 optext:v=>String(v).trim()?v:undefined,
 bool:(v,el)=>el.checked,
 pair:v=>{const t=String(v).trim();if(!t)return undefined;const p=t.split(/[,~]/).map(specNum);return p.length===2&&p.every(Number.isFinite)?p:NaN},
 ticks:v=>{const t=String(v).trim();if(!t)return undefined;if(t==='숨김')return false;const p=t.split(',').map(specNum);return p.every(Number.isFinite)?p:NaN},
 view:v=>{const p=String(v).split(',').map(specNum);return p.length===4&&p.every(Number.isFinite)&&p[0]<p[1]&&p[2]<p[3]?p:NaN},
 points:v=>{const rows=String(v).split(';').map(x=>x.trim()).filter(Boolean).map(r=>r.split(',').map(specNum));return rows.length>=2&&rows.every(r=>r.length===2&&r.every(Number.isFinite))?rows:NaN},
 marks:v=>{const t=String(v).trim();if(!t)return undefined;const rows=t.split(';').map(x=>x.trim()).filter(Boolean).map(r=>{const m=r.match(/^(\S+)\s+(.+)$/);if(!m)return null;const n=specNum(m[1]);return Number.isFinite(n)?[n,m[2].trim()]:null});return rows.every(Boolean)?rows:NaN},
};
const specShow={
 pair:v=>Array.isArray(v)?v.join(', '):'',ticks:v=>v===false?'숨김':Array.isArray(v)?v.join(', '):'',view:v=>Array.isArray(v)?v.join(', '):'',
 points:v=>Array.isArray(v)?v.map(p=>p.join(', ')).join('; '):'',marks:v=>Array.isArray(v)?v.map(p=>`${p[0]} ${p[1]}`).join('; '):'',
};
function specInput(spec,base,key,kind,attrs=''){
 const rel=Array.isArray(key)?key:[key],path=[...base,...rel],value=specGet(spec,rel);  // spec은 이 그래프, path는 명세 전체에서의 자리
 const shown=specShow[kind]?specShow[kind](value):specFmt(value);
 const numeric=['num','numnull','opt'].includes(kind);
 return `<input data-spec-path="${esc(JSON.stringify(path))}" data-spec-kind="${kind}" value="${esc(shown)}" ${numeric?'inputmode="decimal"':''} ${attrs}>`;
}
function specField(spec,base,key,kind,label,hint='',cls=''){
 return `<label class="spec-field ${cls}"><span>${label}</span>${specInput(spec,base,key,kind,hint?`placeholder="${esc(hint)}"`:'')}</label>`;
}
function specOp(op,base,label,extra=''){return `<button type="button" class="small-btn" data-spec-op="${op}" data-spec-base="${esc(JSON.stringify(base))}" ${extra}>${label}</button>`}

function specAxis(spec,base,axis,name){
 return `<div class="spec-axis"><b>${name}</b>${specField(spec,base,[axis,'label'],'optext','이름','예: (%)')}${specField(spec,base,[axis,'min'],'opt','최솟값','자동')}${specField(spec,base,[axis,'max'],'opt','최댓값','자동')}${specField(spec,base,[axis,'step'],'opt','간격','자동')}${specField(spec,base,[axis,'ticks'],'ticks','눈금 값','자동 · 예: 0, 30, 60 · 숨김')}${axis==='y'?specField(spec,base,[axis,'break'],'pair','물결로 자를 구간','예: -50, -10'):''}</div>`;
}
function specChart(g,base){
 const kind=g.chart;
 if(kind==='pie'){
  const rows=(g.slices||[]).map((s,i)=>`<tr><td>${specInput(g,base,['slices',i,'name'],'text','aria-label="조각 이름"')}</td><td>${specInput(g,base,['slices',i,'value'],'num','aria-label="조각 값"')}</td></tr>`).join('');
  return `<table class="spec-table"><thead><tr><th>조각</th><th>값</th></tr></thead><tbody>${rows}</tbody></table><div class="spec-ops">${specOp('add-slice',base,'+ 조각')}${specOp('del-slice',base,'− 마지막 조각')}</div><div class="spec-axis">${specField(g,base,'unit','optext','단위','예: %')}${specField(g,base,'title','optext','제목','')}</div>`;
 }
 if(kind==='scatter'){
  const pts=(g.points||[]).map((p,i)=>`<tr><td>${specInput(g,base,['points',i,'label'],'text','aria-label="점 이름"')}</td><td>${specInput(g,base,['points',i,'x'],'num','aria-label="가로 값"')}</td><td>${specInput(g,base,['points',i,'y'],'num','aria-label="세로 값"')}</td></tr>`).join('');
  const lines=(g.lines||[]).map((l,i)=>`<tr><td>${specInput(g,base,['lines',i,'name'],'text','aria-label="선 이름"')}</td><td colspan="2">${specInput(g,base,['lines',i,'points'],'points','aria-label="선의 점 (x, y; x, y)"')}</td></tr>`).join('');
  return `${pts?`<table class="spec-table"><thead><tr><th>점</th><th>가로 값</th><th>세로 값</th></tr></thead><tbody>${pts}</tbody></table>`:''}${lines?`<table class="spec-table"><thead><tr><th>선</th><th colspan="2">점 목록 · x, y; x, y</th></tr></thead><tbody>${lines}</tbody></table>`:''}<div class="spec-ops">${g.points?specOp('add-point',base,'+ 점')+specOp('del-point',base,'− 마지막 점'):''}</div>${specAxis(g,base,'x','가로축')}${specAxis(g,base,'y','세로축')}`;
 }
 const series=(g.series||[]).filter(s=>s&&typeof s==='object');
 const head=`<tr><th>항목</th>${series.map((s,j)=>`<th>${specInput(g,base,['series',j,'name'],'text','aria-label="계열 이름"')}</th>`).join('')}</tr>`;
 const rows=(g.categories||[]).map((c,i)=>`<tr><th>${specInput(g,base,['categories',i],'text','aria-label="항목 이름"')}</th>${series.map((s,j)=>`<td>${specInput(g,base,['series',j,'values',i],'numnull',`aria-label="${esc(String(s.name||'계열'))} ${esc(String(c))} 값" placeholder="빈 값"`)}</td>`).join('')}</tr>`).join('');
 const sums=kind==='band'?`<p class="hint">띠그래프는 줄마다 합이 ${g.total??100}이어야 합니다.</p>`:'';
 return `<div class="spec-table-wrap"><table class="spec-table"><thead>${head}</thead><tbody>${rows}</tbody></table></div>${sums}<div class="spec-ops">${specOp('add-cat',base,'+ 항목')}${specOp('del-cat',base,'− 마지막 항목')}${specOp('add-series',base,'+ 계열')}${specOp('del-series',base,'− 마지막 계열')}</div>${specAxis(g,base,'y','세로축')}${kind==='line'?`<div class="spec-axis"><b>가로축</b>${specField(g,base,['x','label'],'optext','이름','예: (년)')}</div>`:''}<div class="spec-axis">${specField(g,base,'title','optext','제목','')}<label class="spec-field spec-check">${specInput(g,base,'values','bool',`type="checkbox" ${g.values?'checked':''}`)}<span>막대·점 위에 값 쓰기</span></label></div>`;
}
function specFunction(g,base){
 const ends=(path,i)=>{const v=(specGet(g,[...path])||[])[i]||'none';return `<select data-spec-path="${esc(JSON.stringify([...base,...path,i]))}" data-spec-kind="text" aria-label="${i?'오른쪽':'왼쪽'} 끝점">${[['none','표시 없음'],['closed','● 닫힘'],['open','○ 열림']].map(([k,l])=>`<option value="${k}" ${v===k?'selected':''}>${l}</option>`).join('')}</select>`};
 const rows=(g.curves||[]).map((c,i)=>`<tr><td>${specInput(g,base,['curves',i,'expr'],'text','aria-label="식" placeholder="예: x**2-2*x"')}</td><td>${specInput(g,base,['curves',i,'domain'],'pair','aria-label="구간" placeholder="전체"')}</td><td>${ends(['curves',i,'ends'],0)}</td><td>${ends(['curves',i,'ends'],1)}</td><td>${specInput(g,base,['curves',i,'label'],'optext','aria-label="곡선 이름" placeholder="예: $y=f(x)$"')}</td></tr>`).join('');
 return `<div class="spec-table-wrap"><table class="spec-table"><thead><tr><th>식 (x의 식)</th><th>구간</th><th>왼쪽 끝</th><th>오른쪽 끝</th><th>이름</th></tr></thead><tbody>${rows}</tbody></table></div><div class="spec-ops">${specOp('add-curve',base,'+ 곡선')}${specOp('del-curve',base,'− 마지막 곡선')}</div><div class="spec-axis">${specField(g,base,'view','view','보이는 범위','x최소, x최대, y최소, y최대','wide')}${specField(g,base,'x_ticks','marks','x축 눈금','예: 2 $2$; 3 $a$','wide')}${specField(g,base,'y_ticks','marks','y축 눈금','예: -1 $-1$','wide')}</div>`;
}
function specFormHtml(locked){
 const spec=specParse(locked);if(!spec)return '';
 const graphs=specGraphs(spec);if(!graphs.length)return '';
 const parts=graphs.map(([base,g],n)=>{
  const name=g.type==='function'?'함수 그래프':(SPEC_CHART_NAMES[g.chart]||'그래프');
  const title=(g.caption?g.caption+' ':graphs.length>1?`${n+1}. `:'')+name;
  return `<fieldset class="spec-graph"><legend>${esc(title)}</legend>${g.type==='function'?specFunction(g,base):specChart(g,base)}</fieldset>`;
 }).join('');
 return `<section class="spec-form" aria-label="그래프 수치 입력"><div class="spec-form-head"><b>그래프 수치</b><span class="hint">칸을 고치면 명세가 바로 바뀝니다. 다시 그려도 옮기거나 고친 글씨는 그대로 둡니다.</span></div>${parts}<p class="spec-errors" role="status" data-spec-errors></p><figure class="spec-preview" data-spec-preview hidden><img alt="고친 수치로 그린 미리보기"><figcaption>미리보기 · 글씨는 명세 기본 자리</figcaption></figure></section>`;
}
function specFieldFor(section){return section?.closest('.image-plan-fields')?.querySelector('[data-field="image_locked"]')||document.querySelector('[data-field="image_locked"]')}
function specWrite(section,spec,rebuild){
 const field=specFieldFor(section);if(!field)return;
 field.value=SPEC_PREFIX+' '+JSON.stringify(spec);specEd.writing=true;
 try{field.dispatchEvent(new Event('input',{bubbles:true}))}finally{specEd.writing=false}
 if(rebuild)specRebuild(section,field.value);
 specSchedulePreview(section);
}
function specRebuild(section,locked){
 const html=specFormHtml(locked);if(!section)return;
 if(!html){section.remove();return}
 const holder=document.createElement('div');holder.innerHTML=html;const next=holder.firstElementChild;section.replaceWith(next);specSchedulePreview(next,0);
}
function specSchedulePreview(section,delay=450){clearTimeout(specEd.timer);specEd.timer=setTimeout(()=>specLoadPreview(section),delay)}
async function specLoadPreview(section){
 if(!section?.isConnected)section=document.querySelector('.spec-form');if(!section)return;
 const field=specFieldFor(section),request=++specEd.request,errors=section.querySelector('[data-spec-errors]'),fig=section.querySelector('[data-spec-preview]');
 if(!field)return;
 try{
  const result=await api('/api/diagram-preview',{locked:field.value});
  if(request!==specEd.request)return;
  errors.textContent=(result.errors||[]).join(' / ');
  if(result.png){fig.querySelector('img').src=result.png;fig.hidden=false}else fig.hidden=true;
 }catch(error){if(request===specEd.request){errors.textContent=error.message;fig.hidden=true}}
}

document.addEventListener('input',e=>{
 const el=e.target.closest?.('[data-spec-path]');
 if(!el){
  if(e.target.matches?.('[data-field="image_locked"]')&&!specEd.writing){const section=document.querySelector('.spec-form');clearTimeout(specEd.rebuild);specEd.rebuild=setTimeout(()=>{if(section)specRebuild(section,e.target.value);else if(specFormHtml(e.target.value))render()},500)}
  return;
 }
 if(el.type==='checkbox')return;  // change 이벤트에서 처리
 specApply(el);
},true);
document.addEventListener('change',e=>{const el=e.target.closest?.('[data-spec-path]');if(el&&(el.type==='checkbox'||el.tagName==='SELECT'))specApply(el)},true);
function specApply(el){
 const section=el.closest('.spec-form'),field=specFieldFor(section),spec=field&&specParse(field.value);if(!spec)return;
 const value=SPEC_KINDS[el.dataset.specKind](el.value,el);
 if(typeof value==='number'&&Number.isNaN(value)){el.setAttribute('aria-invalid','true');section.querySelector('[data-spec-errors]').textContent='수로 읽을 수 없는 칸이 있습니다. 고칠 때까지 명세에 반영하지 않습니다.';return}
 el.removeAttribute('aria-invalid');
 specSet(spec,JSON.parse(el.dataset.specPath),value);
 specWrite(section,spec,false);
}
document.addEventListener('click',e=>{
 const btn=e.target.closest?.('[data-spec-op]');if(!btn)return;
 const section=btn.closest('.spec-form'),field=specFieldFor(section),spec=field&&specParse(field.value);if(!spec)return;
 const g=specGet(spec,JSON.parse(btn.dataset.specBase));if(!g)return;
 const op=btn.dataset.specOp,series=(g.series||[]).filter(s=>s&&typeof s==='object');
 if(op==='add-cat'){g.categories=[...(g.categories||[]),`항목 ${(g.categories||[]).length+1}`];for(const s of series)s.values=[...(s.values||[]),null]}
 if(op==='del-cat'){if((g.categories||[]).length<=1)return toast('항목은 하나 이상 있어야 합니다.');g.categories.pop();for(const s of series)s.values?.pop()}
 if(op==='add-series'){g.series=[...series,{name:`계열 ${series.length+1}`,values:(g.categories||[]).map(()=>null)}]}
 if(op==='del-series'){if(series.length<=1)return toast('계열은 하나 이상 있어야 합니다.');g.series=series.slice(0,-1)}
 if(op==='add-slice')g.slices=[...(g.slices||[]),{name:`조각 ${(g.slices||[]).length+1}`,value:0}];
 if(op==='del-slice'){if((g.slices||[]).length<=2)return toast('원그래프 조각은 두 개 이상 있어야 합니다.');g.slices.pop()}
 if(op==='add-point')g.points=[...(g.points||[]),{label:String.fromCharCode(65+(g.points||[]).length%26),x:0,y:0}];
 if(op==='del-point'){if((g.points||[]).length<=1)return toast('점은 하나 이상 있어야 합니다.');g.points.pop()}
 if(op==='add-curve')g.curves=[...(g.curves||[]),{expr:'x'}];
 if(op==='del-curve'){if((g.curves||[]).length<=1)return toast('곡선은 하나 이상 있어야 합니다.');g.curves.pop()}
 specWrite(section,spec,true);
},true);

// 편집 가능한 그림 계획 칸에서 SVG 규칙 칸 바로 위에 붙인다. JSON 칸은 "직접 고칠 때"로 이름을 바꿔 남긴다.
const specBaseImagePlanFields=imagePlanFields;
imagePlanFields=function(c){
 const html=specBaseImagePlanFields(c);
 if(html.includes('image-plan-readonly'))return html;
 const form=specFormHtml(c.image_locked);if(!form)return html;
 const at=html.indexOf('<label id="lockedField"');if(at<0)return html;
 return html.slice(0,at)+form+html.slice(at).replace('>SVG 규칙<textarea','>명세 JSON · 직접 고칠 때만<textarea');
};
new MutationObserver(()=>{for(const section of document.querySelectorAll('.spec-form:not([data-spec-ready])')){section.dataset.specReady='1';specSchedulePreview(section,0)}}).observe(document.body,{childList:true,subtree:true});

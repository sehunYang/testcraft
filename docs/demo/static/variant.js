'use strict';
// 기출 변형: 문항 추가의 셋째 방식. 원본(기출 팩 또는 올린 그림·PDF)을 고르고, 교사가 고른 변형 방식만 AI에 전한다.
(()=>{
const METHODS=[['numbers','수치·조건만 바꾸기','같은 상황에서 값과 정답만 바꿉니다.'],['situation','상황 바꾸고 원리 유지','묻는 원리는 같게, 상황·소재를 새로 정합니다.'],['form','유형·난이도 바꾸기','아래 목표 유형·난이도로 바꿉니다.']];
const side={open:false,key:''};
const vs={pack:null,list:[],subject:'',filter:'',picked:null,upload:null};
// 기출 묶음은 설치 파일로 나눠 주지 않는다(평가원 저작권). 묶음이 없으면 교사가 평가원 홈페이지에서 직접 받는다.
const loadPack=()=>fetch('/api/kice/index?subject=__none__').then(r=>r.json()).then(p=>{vs.pack=p;return p});
loadPack().catch(()=>{});
const html=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const draftVariant=d=>{d.variant=d.variant&&typeof d.variant==='object'?d.variant:{methods:[],memo:'',source:null};d.variant.methods=Array.isArray(d.variant.methods)?d.variant.methods:[];return d.variant};
const isVariant=()=>state.authoringDraft?.mode==='variant';
const persist=()=>{if(typeof authoringPersistLocal==='function')authoringPersistLocal()};

// 1) 문항 작성 방식 창에 셋째 버튼
function injectChoice(){const box=document.querySelector('#authoringChoiceDialog .authoring-choice-options');if(!box||box.querySelector('[data-authoring-choice="variant"]'))return;
 const b=document.createElement('button');b.type='button';b.dataset.authoringChoice='variant';b.innerHTML='<span>⟲</span><b>기출 변형</b><small>기출 문항을 골라 수치·상황·유형을 바꾼 새 문항을 만듭니다.</small>';box.append(b)}
injectChoice();

// 2) 기존 작성 흐름에 끼워 넣기
const baseStart=authoringStart,baseView=authoringDraftView,baseError=authoringDraftError,baseApply=authoringApplyDraft;
authoringStart=function(mode,targetId=null){const existing=targetId?state.exam?.cards.find(c=>c.id===targetId):null;if(existing?.authoring_mode==='variant')mode='variant';baseStart(mode,targetId);if(mode==='variant'&&state.authoringDraft){state.authoringDraft.persistMode='variant';draftVariant(state.authoringDraft.draft);persist();render()}};
authoringDraftView=function(){return isVariant()?view():baseView()};
authoringDraftError=function(){if(!isVariant())return baseError();const d=state.authoringDraft.draft,v=draftVariant(d);
 if(!v.source?.image)return {key:'variant-source',message:'변형할 원본 기출을 먼저 골라 주세요.'};
 if(!v.methods.length)return {key:'variant-method',message:'변형 방식을 하나 이상 골라 주세요.'};
 for(const [key,label] of [['type','문항 유형'],['difficulty','난이도']])if(!String(d[key]||'').trim())return {key,message:label+'을(를) 골라 주세요.'};return null};
authoringApplyDraft=function(){if(!isVariant())return baseApply();const session=state.authoringDraft,d=session.draft,invalid=authoringDraftError();if(invalid)throw Error(invalid.message);
 let id=session.committedCardId||session.targetCardId||session.reuseCardId,index=id?state.exam.cards.findIndex(c=>c.id===id):-1,card=index>=0?state.exam.cards[index]:null;const isNew=!card;
 if(!card){card=authoringBlankCard(session.committedCardId||session.reuseCardId||(typeof uxMakeId==='function'?uxMakeId():crypto.randomUUID().replaceAll('-','').slice(0,16)),state.exam.cards.length+1);index=state.exam.cards.length;state.exam.cards.push(card)}
 const before=JSON.stringify([card.standard,card.type,card.difficulty,card.idea,card.variant]);
 for(const key of ['standard','standard_name','standard_note','type','difficulty','idea','format'])card[key]=d[key]??'';
 card.authoring_mode='variant';card.ai_requested=true;card.variant=structuredClone(draftVariant(d));card.no=card.no||index+1;
 session.committedCardId=card.id;state.exam.cards[index]=card;state.card=index;session.contentChanged=isNew||before!==JSON.stringify([card.standard,card.type,card.difficulty,card.idea,card.variant]);return card};

// 3) 작성 화면
function sourceBlock(v){const s=v.source;if(!s?.image)return `<div class="variant-source empty" data-variant-anchor="variant-source"><p>아직 원본을 고르지 않았습니다.</p></div>`;
 return `<div class="variant-source" data-variant-anchor="variant-source"><img alt="원본 기출" src="/api/sources/${html(state.exam.id)}/${html(s.image)}"><div><b>${html(s.label)}</b><small>${s.kind==='kice'?'평가원 기출 · 해설지에만 출처를 적습니다.':'올린 원본 · 해설지에 이 이름으로 출처를 적습니다.'}</small></div></div>`}
function view(){const session=state.authoringDraft,d=session.draft,v=draftVariant(d),formOn=v.methods.includes('form');
 return `<section class="design-authoring variant-authoring"><div class="authoring-heading"><button type="button" class="small-btn" data-authoring-cancel>← 문항 목록</button><div><div class="eyebrow">VARIANT DRAFT</div><h2>${session.targetCardId?`${html(String(d.no).padStart(2,'0'))}번 문항`:'새 문항'} · 기출 변형</h2><p>원본 기출과 변형 방식을 저장합니다. AI 생성은 저장 후 원할 때 시작합니다. 원본 문장·그림은 시험지에 들어가지 않습니다.</p></div></div>
 <form id="authoringDraftForm" class="authoring-draft-form" novalidate><section class="panel"><div class="panel-body"><div class="authoring-fields">
 <fieldset class="authoring-group full"><legend>원본 기출</legend>${sourceBlock(v)}<div class="variant-source-actions"><button type="button" class="secondary" data-variant-open-pack>${vs.pack&&!vs.pack.available?'평가원 기출 받기':'기출 목록에서 고르기'}</button><label class="secondary file-btn">그림·PDF 올리기<input type="file" accept="image/png,image/jpeg,application/pdf" data-variant-file hidden></label></div></fieldset>
 <fieldset class="authoring-group full" data-variant-anchor="variant-method"><legend>변형 방식 <span class="muted">하나 이상 고르세요</span></legend><div class="variant-methods">${METHODS.map(([k,t,h])=>`<label class="variant-method ${v.methods.includes(k)?'on':''}"><input type="checkbox" data-variant-method="${k}" ${v.methods.includes(k)?'checked':''}><b>${t}</b><small>${h}</small></label>`).join('')}</div>
 <label class="full">교사 메모 <span class="muted">선택 사항</span><textarea data-variant-memo maxlength="2000" placeholder="예: 그래프 대신 표로, 오답 ③을 매력적인 오답으로">${html(v.memo||'')}</textarea></label></fieldset>
 <fieldset class="authoring-group full"><legend>${formOn?'목표 유형·난이도':'유형·난이도 <span class="muted">원본과 같게 둡니다</span>'}</legend><div class="fields">${authoringSelect('type','문항 유형',[['','선택해 주세요'],...(state.boot?.types||[]).map(x=>[x,x])],d)}${authoringSelect('difficulty','난이도',[['','선택해 주세요'],['상','상'],['중','중'],['하','하']],d)}
 <label class="full">성취기준 <span class="muted">비우면 AI가 원본에 맞는 성취기준을 검토 의견으로 제안합니다</span><select data-authoring-field="standard"><option value="">AI 제안 받기</option>${Object.entries(state.standards||{}).filter(([,x])=>x.subject===state.exam?.subject).map(([code,x])=>`<option value="${html(code)}" ${d.standard===code?'selected':''}>${html(code)} · ${html(x.name)}</option>`).join('')}</select></label>
 <label class="full">핵심 아이디어 <span class="muted">선택 사항</span><textarea data-authoring-field="idea" placeholder="원본에서 꼭 살릴 평가 요소가 있으면 적어 주세요.">${html(d.idea||'')}</textarea></label></div></fieldset>
 </div></div></section><div class="review-action-dock" id="taskActionBar"><div class="task-action"><span>원본과 변형 방식을 저장하고 생성 대기에 추가합니다.</span><button type="button" class="secondary" data-authoring-cancel>목록으로 돌아가기</button><button type="submit" class="primary">생성 대기에 추가</button></div></div></form></section>`}

// 4) 기출 목록 창
function picker(){let dlg=document.querySelector('#variantPackDialog');if(!dlg){dlg=document.createElement('dialog');dlg.id='variantPackDialog';dlg.className='variant-pack-dialog';document.body.append(dlg)}return dlg}
async function openPack(){const dlg=picker();if(!vs.pack?.available)await loadPack();
 if(!vs.pack.available){if(!dlg.open)dlg.showModal();await pollFetch();return}
 const name=typeof subjectLabel==='function'?subjectLabel():'';vs.subject=vs.subject||vs.pack.subjects.find(s=>name.replace(/\s/g,'').includes(s.replace(/[ⅠⅡ]/g,''))&&name.includes(s.slice(-1)))||vs.pack.subjects.find(s=>name.includes(s.replace(/[ⅠⅡ]/g,'')))||vs.pack.subjects[0];
 await loadSubject();dlg.showModal();drawPack()}
// 4-1) 평가원에서 받기: 이 PC가 평가원 홈페이지에서 과학탐구 문제지를 받아 문항별로 자른다
let fetchTimer=0;
async function pollFetch(){clearTimeout(fetchTimer);const dlg=picker();if(!dlg.open)return;const st=await (await fetch('/api/kice/status')).json();
 if(st.finished&&!st.running&&!st.error){await loadPack();if(vs.pack.available&&!st.failed.length){await openPack();return}}
 const pct=st.total?Math.round(st.done/st.total*100):0;
 dlg.innerHTML=`<div class="dialog-top"><div><div class="eyebrow">KICE</div><h2>평가원 기출 받기</h2></div><button type="button" class="icon-btn" data-variant-close aria-label="닫기">×</button></div>
 <p class="variant-fetch-note">${html(st.notice)}</p>
 <ul class="variant-fetch-facts"><li>과학탐구 8과목(물리학·화학·생명과학·지구과학 Ⅰ·Ⅱ), ${st.years[0]}~${st.years[1]}학년도 수능·6월·9월 모의평가</li><li>받는 양 약 300MB, 만들어지는 묶음 약 150MB · 수십 분 걸릴 수 있습니다</li><li>창을 닫아도 계속 받습니다. 멈춘 뒤 다시 누르면 이어서 받습니다.</li></ul>
 ${st.running||st.finished?`<div class="variant-fetch-progress"><progress max="100" value="${pct}"></progress><span>${st.done}/${st.total||'?'}개 시험 · ${st.questions}문항</span></div><p>${html(st.stage)}</p>`:''}
 ${st.error?`<p class="warn">${html(st.error)}</p>`:''}
 ${st.failed.length?`<details><summary>잘 나누지 못한 시험지 ${st.failed.length}개</summary><ul>${st.failed.map(f=>`<li>${html(f)}</li>`).join('')}</ul></details>`:''}
 <div class="dialog-actions"><button type="button" data-variant-close>닫기</button>${st.running?'<button type="button" data-variant-fetch-cancel>멈추기</button>':`${vs.pack?.available?'<button type="button" data-variant-open-pack>기출 목록 보기</button>':''}<button type="button" class="primary" data-variant-fetch-start>${st.finished?'다시 받기':'동의하고 받기'}</button>`}</div>`;
 if(st.running)fetchTimer=setTimeout(()=>run(pollFetch),1500)}
async function loadSubject(){vs.list=(await (await fetch('/api/kice/index?subject='+encodeURIComponent(vs.subject))).json()).questions;vs.picked=null}
const roundName=r=>r.round==='수능'?'수능':r.round+' 모평';
function drawPack(){const dlg=picker(),words=vs.filter.trim().split(/\s+/).filter(Boolean),rows=vs.list.filter(r=>{const hay=`${r.year} ${roundName(r)} ${r.no}번 ${r.label} ${r.form} ${r.points?r.points+'점':''} ${r.ask}`;return words.every(w=>hay.includes(w))}).slice(0,400);
 dlg.innerHTML=`<div class="dialog-top"><div><div class="eyebrow">KICE</div><h2>기출 목록에서 고르기</h2></div><button type="button" class="icon-btn" data-variant-close aria-label="닫기">×</button></div>
 <div class="variant-pack-tools"><select data-variant-subject>${vs.pack.subjects.map(s=>`<option ${s===vs.subject?'selected':''}>${s}</option>`).join('')}</select><input type="search" data-variant-filter placeholder="예: 2025 수능, 합답형, 12번" value="${html(vs.filter)}"></div>
 <div class="variant-pack-body"><ol class="variant-pack-list">${rows.map(r=>`<li><button type="button" data-variant-pick="${html(r.key)}" class="${vs.picked===r.key?'on':''}"><b>${r.year} ${roundName(r)} ${r.no}번</b><small>${html(r.form)}${r.points?` · ${r.points}점`:''}${r.graphic&&r.graphic!=='없음'?' · 그림':''}</small></button></li>`).join('')||'<li class="muted">찾는 문항이 없습니다.</li>'}</ol>
 <div class="variant-pack-preview">${vs.picked?`<img alt="기출 미리보기" src="/api/kice/image?key=${encodeURIComponent(vs.picked)}">`:'<p class="muted">왼쪽에서 문항을 고르면 원본이 보입니다.</p>'}</div></div>
 <div class="dialog-actions"><button type="button" data-variant-close>취소</button><button type="button" class="primary" data-variant-use ${vs.picked?'':'disabled'}>이 문항으로 변형</button></div>`}
async function useSource(payload){const {source}=await api('/api/variant-source',{exam_id:state.exam.id,...payload});const d=state.authoringDraft.draft,v=draftVariant(d);v.source=source;
 if(!d.type&&source.form)d.type=source.form==='합답형'?'합답형':'최선답형';if(!d.difficulty)d.difficulty='중';persist();render()}

// 5) 그림·PDF 올리기: PDF는 쪽 그림으로 바꾼 뒤, 문항 영역을 끌어 자른다
function fileData(file){return new Promise((ok,fail)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=fail;r.readAsDataURL(file)})}
function cropDialog(){let dlg=document.querySelector('#variantCropDialog');if(!dlg){dlg=document.createElement('dialog');dlg.id='variantCropDialog';dlg.className='variant-pack-dialog';document.body.append(dlg)}return dlg}
async function openUpload(file){if(file.size>25*1024*1024){toast('원본 파일은 25MB 이하로 올려 주세요.');return}const data=await fileData(file),pdf=/\.pdf$/i.test(file.name)||file.type==='application/pdf';
 vs.upload={name:file.name.replace(/\.[^.]+$/,''),data,pdf,page:1,box:null};drawCrop()}
function drawCrop(){const u=vs.upload,dlg=cropDialog();
 dlg.innerHTML=`<div class="dialog-top"><div><div class="eyebrow">UPLOAD</div><h2>원본 영역 고르기</h2></div><button type="button" class="icon-btn" data-variant-close aria-label="닫기">×</button></div>
 <p>변형할 문항 하나만 끌어서 고르세요. 고르지 않으면 ${u.pdf?'쪽':'그림'} 전체를 씁니다.</p>
 <div class="variant-pack-tools"><label>출처 이름<input data-variant-upload-label value="${html(u.name)}" maxlength="120"></label>${u.pdf?`<label>PDF 쪽<input type="number" min="1" value="${u.page}" data-variant-upload-page style="width:5em"></label><button type="button" class="secondary" data-variant-upload-render>이 쪽 보기</button>`:''}</div>
 <div class="variant-crop"><div class="variant-crop-stage"><img data-variant-crop-img alt="올린 원본" src="${u.preview||(!u.pdf?u.data:'')}"><div class="variant-crop-box" hidden></div></div>${u.pdf&&!u.preview?'<p class="muted">\'이 쪽 보기\'를 누르면 쪽 그림이 나옵니다.</p>':''}</div>
 <div class="dialog-actions"><button type="button" data-variant-close>취소</button><button type="button" class="primary" data-variant-upload-use ${u.pdf&&!u.preview?'disabled':''}>이 영역으로 변형</button></div>`;
 if(!dlg.open)dlg.showModal()}
async function renderPdfPage(){const u=vs.upload;const r=await api('/api/variant-source',{exam_id:state.exam.id,kind:'upload',name:u.name+'.pdf',data:u.data,page:u.page,label:u.name,preview:true});u.preview='/api/sources/'+state.exam.id+'/'+r.source.image;u.previewSource=r.source;u.box=null;drawCrop()}
let drag=null;
window.addEventListener('pointerdown',e=>{const stage=e.target.closest('.variant-crop-stage');if(!stage)return;e.preventDefault();const r=stage.getBoundingClientRect();drag={stage,r,x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height};stage.setPointerCapture?.(e.pointerId)},true);
window.addEventListener('pointermove',e=>{if(!drag)return;const {stage,r}=drag,x=Math.min(1,Math.max(0,(e.clientX-r.left)/r.width)),y=Math.min(1,Math.max(0,(e.clientY-r.top)/r.height)),box=[Math.min(drag.x,x),Math.min(drag.y,y),Math.max(drag.x,x),Math.max(drag.y,y)];vs.upload.box=box;const el=stage.querySelector('.variant-crop-box');el.hidden=false;Object.assign(el.style,{left:box[0]*100+'%',top:box[1]*100+'%',width:(box[2]-box[0])*100+'%',height:(box[3]-box[1])*100+'%'})},true);
window.addEventListener('pointerup',()=>{if(drag&&vs.upload?.box&&(vs.upload.box[2]-vs.upload.box[0]<.03||vs.upload.box[3]-vs.upload.box[1]<.03)){vs.upload.box=null;drag.stage.querySelector('.variant-crop-box').hidden=true}drag=null},true);
async function useUpload(){const u=vs.upload,label=document.querySelector('[data-variant-upload-label]')?.value||u.name;
 await useSource({kind:'upload',name:u.pdf?u.name+'.pdf':u.name+'.png',data:u.data,page:u.page,label,crop:u.box||null});cropDialog().close();vs.upload=null}

// 6) 이벤트 (window 캡처 단계: 작성 화면의 다른 처리보다 먼저 받는다)
const run=fn=>Promise.resolve().then(fn).catch(err=>toast(err.message||String(err)));
window.addEventListener('click',e=>{const t=e.target;
 if(t.closest('[data-variant-open-pack]')){e.preventDefault();e.stopImmediatePropagation();run(openPack);return}
 if(t.closest('[data-variant-fetch-start]')){e.preventDefault();e.stopImmediatePropagation();run(async()=>{await api('/api/kice/download',{});await pollFetch()});return}
 if(t.closest('[data-variant-fetch-cancel]')){e.preventDefault();e.stopImmediatePropagation();run(async()=>{await api('/api/kice/cancel',{});await pollFetch()});return}
 if(t.closest('[data-variant-side]')){e.preventDefault();e.stopImmediatePropagation();side.open=!side.open;syncSide();document.querySelectorAll('.variant-summary [data-variant-side]').forEach(x=>x.textContent=side.open?'원본 닫기':'원본 나란히 보기');return}
 if(t.closest('[data-variant-close]')){e.preventDefault();t.closest('dialog')?.close();return}
 const pick=t.closest('[data-variant-pick]');if(pick){e.preventDefault();vs.picked=pick.dataset.variantPick;drawPack();return}
 if(t.closest('[data-variant-use]')){e.preventDefault();run(async()=>{await useSource({kind:'kice',key:vs.picked});picker().close()});return}
 if(t.closest('[data-variant-upload-render]')){e.preventDefault();run(renderPdfPage);return}
 if(t.closest('[data-variant-upload-use]')){e.preventDefault();run(useUpload);return}
},true);
window.addEventListener('change',e=>{const t=e.target;
 if(t.matches('[data-variant-method]')&&isVariant()){e.stopImmediatePropagation();const v=draftVariant(state.authoringDraft.draft),k=t.dataset.variantMethod;v.methods=METHODS.map(m=>m[0]).filter(m=>m===k?t.checked:v.methods.includes(m));persist();render();return}
 if(t.matches('[data-variant-file]')){e.stopImmediatePropagation();const f=t.files?.[0];t.value='';if(f)run(()=>openUpload(f));return}
 if(t.matches('[data-variant-subject]')){vs.subject=t.value;vs.filter='';run(async()=>{await loadSubject();drawPack()});return}
 if(t.matches('[data-variant-upload-page]')){vs.upload.page=Math.max(1,parseInt(t.value)||1);return}
},true);
window.addEventListener('input',e=>{const t=e.target;
 if(t.matches('[data-variant-memo]')&&isVariant()){e.stopImmediatePropagation();draftVariant(state.authoringDraft.draft).memo=t.value;persist();return}
 if(t.matches('[data-variant-filter]')){vs.filter=t.value;const pos=t.selectionStart;drawPack();const f=document.querySelector('[data-variant-filter]');f.focus();f.setSelectionRange(pos,pos);return}
},true);

// 7) 문항 카드에서 원본·바뀐 점 보기
window.variantSummary=function(card){const v=card?.authoring_mode==='variant'?card.variant:null;if(!v?.source)return '';
 return `<div class="variant-summary"><b>기출 변형</b> · ${html(v.source.label)}${v.methods?.length?` · ${v.methods.map(m=>METHODS.find(x=>x[0]===m)?.[1]).join(', ')}`:''}${v.changes?.length?`<ul>${v.changes.map(c=>`<li data-variant-math="${html(c)}">${html(c)}</li>`).join('')}</ul>`:''}${v.overlap>=(v.methods?.length===1&&v.methods[0]==='numbers'?.5:.25)?`<p class="warn">원본과 겹치는 표현이 많습니다(${Math.round(v.overlap*100)}%).</p>`:''}<span class="variant-summary-actions"><button type="button" class="small-btn" data-variant-side>${side.open?'원본 닫기':'원본 나란히 보기'}</button><a href="/api/sources/${html(state.exam.id)}/${html(v.source.image)}" target="_blank" rel="noopener">새 탭에서 보기 ↗</a></span></div>`};

// 7-1) 원본 나란히 보기: 화면 오른쪽에 원본을 붙여 두고 문항을 검토·수정한다. 문항을 옮기면 그 문항의 원본으로 바뀐다
function sidePanel(){let el=document.querySelector('#variantSidePanel');if(!el){el=document.createElement('aside');el.id='variantSidePanel';el.className='variant-side-panel';el.hidden=true;document.body.append(el)}return el}
function syncSide(){const el=sidePanel(),card=state.exam?.cards?.[state.card],s=card?.authoring_mode==='variant'?card.variant?.source:null,show=side.open&&!!s?.image&&!!document.querySelector('.variant-summary');   // 검토 화면의 변형 문항에서만 붙여 둔다
 document.body.classList.toggle('variant-side-open',show);el.hidden=!show;if(!show){side.key='';return}
 const key=state.exam.id+'/'+s.image;if(side.key===key)return;side.key=key;
 el.innerHTML=`<div class="variant-side-head"><div><div class="eyebrow">ORIGINAL</div><b>${html(s.label)}</b></div><button type="button" class="icon-btn" data-variant-side aria-label="원본 닫기">×</button></div><div class="variant-side-body"><img alt="원본 기출" src="/api/sources/${html(key)}"></div>`}

// 바뀐 점의 $…$ 수식을 미리보기와 같은 방식으로 그린다
const mathCache=new Map();
function drawMath(){for(const li of document.querySelectorAll('.variant-summary [data-variant-math]:not([data-ready])')){
 const text=li.dataset.variantMath;li.dataset.ready='1';if(typeof previewNeedsMath!=='function'||!previewNeedsMath(text))continue;
 const job=mathCache.get(text)||api('/api/math-preview',{text}).then(r=>r.segments);mathCache.set(text,job);
 job.then(seg=>{if(Array.isArray(seg)&&li.isConnected)li.innerHTML=previewMathMarkup(seg,text)}).catch(()=>{mathCache.delete(text)})}}
new MutationObserver(()=>{if(side.open)syncSide();if(document.querySelector('.variant-summary [data-variant-math]:not([data-ready])'))drawMath()}).observe(document.body,{childList:true,subtree:true});

})();

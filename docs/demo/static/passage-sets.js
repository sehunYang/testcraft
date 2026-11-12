'use strict';
// 지문 세트(연계 문항): one or two passages — (가)·(나) — printed once as "[n~m] 다음 글을 읽고 물음에 답하시오."
// and read by 2~5 consecutive questions. Teachers paste textbook passages; [[구절]] is printed underlined.
(()=>{
 const SET_MAX=5,SET_MIN=2;
 const newId=()=>crypto.randomUUID().replaceAll('-','').slice(0,16);
 const sets=()=>state.exam?.sets||[];
 const setOf=c=>c?.set_id?sets().find(s=>s.id===c.set_id):null;
 const range=id=>{const nos=(state.exam?.cards||[]).filter(c=>c.set_id===id).map(c=>c.no);return nos.length?[Math.min(...nos),Math.max(...nos)]:null};
 const rangeText=r=>r?(r[0]===r[1]?`[${r[0]}]`:`[${r[0]}~${r[1]}]`):'';
 const headText=s=>`${rangeText(range(s.id))} ${s.passages.length===2?'(가)와 (나)를':'다음 글을'} 읽고 물음에 답하시오.`;
 const passageHtml=text=>esc(text).replace(/\[\[(.+?)\]\]/g,'<u>$1</u>').replace(/\n/g,'<br>');
 const dialog=document.createElement('dialog');dialog.id='passageSetDialog';dialog.className='passage-set-dialog';document.body.append(dialog);
 let editing=null,draft=null;

 function passageFields(p,i,count){
  const label=count===2?['(가)','(나)'][i]:'';
  return `<fieldset class="ps-passage-field"><legend>${label?`지문 ${label}`:'지문'}</legend><textarea data-ps-content="${i}" rows="9" placeholder="교과서·참고서 지문을 붙여 넣으세요. 시의 연 구분은 빈 줄로 둡니다.">${esc(p.content||'')}</textarea><input data-ps-source="${i}" maxlength="300" value="${esc(p.source||'')}" placeholder="출처 · 예: 윤동주, 「서시」"></fieldset>`;
 }
 function questionRows(n){
  const types=(state.boot?.types||['최선답형']).filter(t=>!(state.boot?.subjective_types||[]).includes(t));   // 세트는 선택형끼리
  return Array.from({length:n},(_,i)=>{const q=draft.questions[i]||{};return `<div class="ps-question"><b>${i+1}</b><select data-ps-q="type" data-i="${i}">${types.map(t=>`<option ${t===(q.type||'최선답형')?'selected':''}>${esc(t)}</option>`).join('')}</select><select data-ps-q="difficulty" data-i="${i}">${['하','중','상'].map(d=>`<option ${d===(q.difficulty||'중')?'selected':''}>${d}</option>`).join('')}</select><input data-ps-q="idea" data-i="${i}" value="${esc(q.idea||'')}" placeholder="평가 요소 (비우면 AI가 다른 문항과 겹치지 않게 정함)"></div>`}).join('');
 }
 function paint(){
  const s=editing?sets().find(x=>x.id===editing):null,count=draft.passages.length;
  const standards=Object.entries(state.standards||{}).filter(([,v])=>v.subject===state.exam?.subject);
  dialog.innerHTML=`<form method="dialog" class="ps-form"><div class="dialog-top"><div><div class="eyebrow">PASSAGE SET</div><h2>${s?'지문 편집':'지문 세트 추가'}</h2></div><button type="button" class="icon-btn" data-ps-close aria-label="닫기">×</button></div>
   <p class="hint">시험지에는 “[n~m] 다음 글을 읽고 물음에 답하시오.”와 함께 지문이 한 번만 인쇄됩니다. 밑줄은 [[ ]]로 감쌉니다(예: ㉠[[떠나가는 배]]). AI가 문항에 필요한 밑줄을 더할 수도 있습니다. 학교 시험을 위한 지문 복제는 저작권법 제32조로 허용됩니다.</p>
   <div class="ps-passages">${draft.passages.map((p,i)=>passageFields(p,i,count)).join('')}</div>
   <div class="buttons-wrap"><button type="button" class="small-btn" data-ps-second>${count===2?'지문 (나) 빼기':'지문 (나) 추가'}</button><button type="button" class="small-btn" data-ps-search>저작권 만료 문학 작품 찾기</button></div>
   ${s?'':`<fieldset class="ps-questions"><legend>문항</legend><label>성취기준<select data-ps-standard><option value="">성취기준 선택</option>${standards.map(([code,v])=>`<option value="${esc(code)}" ${code===draft.standard?'selected':''}>${esc(code)} · ${esc(v.name)}</option>`).join('')}</select></label><label>문항 수<select data-ps-count>${[2,3,4,5].map(n=>`<option ${n===draft.count?'selected':''}>${n}</option>`).join('')}</select></label><div class="ps-question-rows">${questionRows(draft.count)}</div></fieldset>`}
   <p class="ps-error" role="alert" hidden></p>
   <div class="buttons-wrap ps-actions"><button type="button" data-ps-close>취소</button><button type="button" class="primary" data-ps-save>${s?'지문 저장':'세트 만들기'}</button></div></form>`;
 }
 function open(setId=null){
  if(!state.exam)return;editing=setId;const s=setId?sets().find(x=>x.id===setId):null;
  draft={passages:s?s.passages.map(p=>({...p})):[{label:'',content:'',source:''}],standard:'',count:3,questions:[]};
  paint();dialog.showModal();
 }
 function readForm(){
  dialog.querySelectorAll('[data-ps-content]').forEach(t=>{draft.passages[+t.dataset.psContent].content=t.value});
  dialog.querySelectorAll('[data-ps-source]').forEach(t=>{draft.passages[+t.dataset.psSource].source=t.value.trim()});
  const std=dialog.querySelector('[data-ps-standard]');if(std)draft.standard=std.value;
  const count=dialog.querySelector('[data-ps-count]');if(count)draft.count=+count.value;
  dialog.querySelectorAll('[data-ps-q]').forEach(el=>{const i=+el.dataset.i;draft.questions[i]={...draft.questions[i],[el.dataset.psQ]:el.value.trim()}});
 }
 function fail(message){const box=dialog.querySelector('.ps-error');box.textContent=message;box.hidden=false}
 async function commit(){
  readForm();
  if(draft.passages.some(p=>!p.content.trim()))return fail('지문 내용을 넣어 주세요.');
  const passages=draft.passages.map((p,i)=>({id:p.id||newId(),label:draft.passages.length===2?['(가)','(나)'][i]:'',content:p.content.replace(/\r\n/g,'\n').replace(/^\n+|\n+$/g,''),source:p.source||''}));
  if(editing){
   const s=sets().find(x=>x.id===editing);s.passages=passages;
   for(const c of state.exam.cards)if(c.set_id===editing)c.review_approved=false;   // the questions read the edited passage
   state.exam.card_approval=null;
  }else{
   if(!draft.standard)return fail('성취기준을 선택해 주세요.');
   if(state.exam.cards.length+draft.count>100)return fail('문항 수는 100개까지입니다.');
   const id=newId(),found=state.standards[draft.standard]||{};
   state.exam.sets=[...sets(),{id,passages}];
   for(let i=0;i<draft.count;i++){
    const q=draft.questions[i]||{},c=authoringBlankCard(newId(),state.exam.cards.length+1);
    Object.assign(c,{standard:draft.standard,standard_name:found.name||'',standard_note:found.note||'',type:q.type||'최선답형',difficulty:q.difficulty||'중',
     idea:q.idea||`지문 세트 ${i+1}번째 문항 · 평가 요소는 같은 세트의 다른 문항과 겹치지 않게 정한다`,authoring_mode:'ai',ai_requested:true,set_id:id});
    state.exam.cards.push(c);
   }
   state.exam.card_approval=null;state.card=state.exam.cards.length-draft.count;
  }
  dialog.close();markDirty(false);await save();render();
 }
 window.passageSets={open,setOf,headText,passageHtml};

 // 위키문헌 search: only works whose authors died long enough ago can be inserted (checked again on the server).
 const finder=document.createElement('dialog');finder.id='literatureDialog';finder.className='literature-dialog';document.body.append(finder);
 let chosen=null;
 finder.innerHTML=`<div class="dialog-top"><div><div class="eyebrow">위키문헌 · 저작권 만료 작품</div><h2>문학 작품 찾기</h2></div><button type="button" class="icon-btn" data-lit-close aria-label="닫기">×</button></div>
  <p class="hint">저작자가 세상을 떠난 지 오래되어 저작권이 끝난 작품만 넣을 수 있습니다. 판본마다 표기가 다르니 넣은 뒤 교과서 표기와 맞춰 주세요.</p>
  <form class="lit-search" data-lit-form><input name="q" maxlength="80" placeholder="작품 이름 또는 저자 · 예: 진달래꽃, 김소월" autocomplete="off"><button class="primary" type="submit">찾기</button></form>
  <div class="lit-results" aria-live="polite"></div>`;
 const results=finder.querySelector('.lit-results');
 async function find(q){
  results.innerHTML='<p class="hint">위키문헌에서 찾는 중…</p>';
  try{
   const found=await api('/api/literature/search',{q});
   if(!found.results.length){results.innerHTML='<p class="hint">찾은 작품이 없습니다. 다른 낱말로 찾아 주세요.</p>';return}
   results.innerHTML=found.results.map((r,i)=>`<button type="button" class="lit-item" data-lit-pick="${i}" ${r.allowed?'':'disabled'}><b>${esc(r.work)}</b><span>${esc(r.author||'작자 미상')}${r.died?` · ${r.died}년 사망`:''}</span><small>${esc(r.title)}</small>${r.allowed?'':`<em>${esc(r.reason)}</em>`}</button>`).join('');
   results._found=found.results;
  }catch(e){results.innerHTML=`<p class="ps-error">${esc(e.message||'찾지 못했습니다.')}</p>`}
 }
 finder.addEventListener('submit',e=>{e.preventDefault();const q=finder.querySelector('[name=q]').value.trim();if(q)find(q)});
 finder.addEventListener('click',async e=>{
  if(e.target.closest('[data-lit-close]')){finder.close();return}
  const pick=e.target.closest('[data-lit-pick]');if(!pick||pick.disabled)return;
  const item=results._found[+pick.dataset.litPick];pick.setAttribute('aria-busy','true');
  try{const text=await api('/api/literature/text',{title:item.title});finder.close();chosen?.(text);if(text.truncated)toast('작품이 길어 앞부분 2만 자만 넣었습니다. 출제할 부분만 남겨 주세요.')}
  catch(err){pick.removeAttribute('aria-busy');pick.insertAdjacentHTML('beforeend',`<em>${esc(err.message||'본문을 가져오지 못했습니다.')}</em>`)}
 });
 window.literatureSearch={open(callback){chosen=callback;finder.showModal();finder.querySelector('[name=q]').focus()}};

 dialog.addEventListener('click',e=>{
  if(e.target.closest('[data-ps-close]')){e.preventDefault();dialog.close();return}
  if(e.target.closest('[data-ps-second]')){readForm();draft.passages=draft.passages.length===2?[draft.passages[0]]:[...draft.passages,{label:'',content:'',source:''}];paint();return}
  if(e.target.closest('[data-ps-search]')){readForm();window.literatureSearch?.open(text=>{const empty=draft.passages.findIndex(p=>!p.content.trim());const i=empty<0?draft.passages.length-1:empty;draft.passages[i]={...draft.passages[i],content:text.content,source:text.source};paint()});return}
  if(e.target.closest('[data-ps-save]')){e.preventDefault();commit().catch(err=>fail(err.message||'저장하지 못했습니다.'));}
 });
 dialog.addEventListener('change',e=>{if(e.target.matches('[data-ps-count]')){readForm();paint()}});

 // The passage shows above the question in the preview, with an edit button.
 const basePreview=preview;
 preview=function(c){
  const html=basePreview(c),s=setOf(c);if(!s)return html;
  const block=`<section class="ps-preview"><p class="ps-head">${esc(headText(s))}<button type="button" class="small-btn" data-ps-edit="${esc(s.id)}">지문 편집</button></p>${s.passages.map(p=>`<div class="material-box ps-passage">${p.label?`<b>${esc(p.label)}</b> `:''}${passageHtml(p.content)}${p.source?`<div class="ps-source">- ${esc(p.source)} -</div>`:''}</div>`).join('')}</section>`;
  return html.replace('<p class="preview-stem',block+'<p class="preview-stem');
 };
 document.addEventListener('click',e=>{
  if(e.target.closest('#addPassageSet')){e.preventDefault();e.stopImmediatePropagation();open();return}
  const edit=e.target.closest('[data-ps-edit]');if(edit){e.preventDefault();e.stopImmediatePropagation();open(edit.dataset.psEdit)}
 },true);

 // A set's questions stay together: dragging one moves the whole set, and a question dropped inside a set lands after it.
 reorderCards=async function(source,target){
  if(source===target)return;if(state.job?.status==='running')throw Error('생성이 끝난 뒤 순서를 변경해 주세요.');await save();
  const cards=state.exam.cards.slice(),active=current()?.id,moving=cards.find(c=>c.id===source),onto=cards.find(c=>c.id===target);if(!moving||!onto)return;
  const group=moving.set_id?cards.filter(c=>c.set_id===moving.set_id):[moving];if(group.includes(onto))return;
  const forward=cards.indexOf(onto)>cards.indexOf(moving),rest=cards.filter(c=>!group.includes(c));
  const block=onto.set_id?rest.filter(c=>c.set_id===onto.set_id):[onto];
  const at=forward?rest.indexOf(block[block.length-1])+1:rest.indexOf(block[0]);
  rest.splice(at,0,...group);state.exam.cards=rest.map((c,i)=>({...c,no:i+1}));
  state.card=state.exam.cards.findIndex(c=>c.id===active);state.exam.card_approval=null;markDirty(false);
  await save();render();toast(group.length>1?'지문 세트를 함께 옮기고 번호를 다시 매겼습니다.':'문항 순서를 저장하고 번호를 다시 매겼습니다.');
 };

 // After any redraw: the toolbar button and set badges on the question list and rail.
 function decorate(){
  if(!state.exam)return;
  const bar=document.querySelector('.design-stage .stage-toolbar .buttons-wrap');
  if(bar&&!bar.querySelector('#addPassageSet')){const b=document.createElement('button');b.id='addPassageSet';b.className='secondary';b.textContent='지문 세트 추가';b.title=`지문 하나로 문항 ${SET_MIN}~${SET_MAX}개를 출제합니다(국어·영어 연계 문항).`;bar.querySelector('#addCard')?.after(b)}
  const badge=c=>{const s=setOf(c);return s?`지문 ${rangeText(range(s.id))}`:''};
  document.querySelectorAll('tr[data-card]').forEach(row=>{const c=state.exam.cards[+row.dataset.card],text=badge(c),cell=row.children[1];if(!cell)return;const old=cell.querySelector('.ps-badge');if(old&&old.textContent===text)return;old?.remove();if(text)cell.insertAdjacentHTML('afterbegin',`<span class="ps-badge">${esc(text)}</span>`)});
  document.querySelectorAll('.item-btn[data-select]').forEach(btn=>{const c=state.exam.cards[+btn.dataset.select],text=badge(c),old=btn.querySelector('.ps-badge');if(old&&old.textContent===text)return;old?.remove();if(text)btn.insertAdjacentHTML('beforeend',`<span class="ps-badge">${esc(text)}</span>`)});
 }
 let pending=false;
 new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;decorate()})}).observe(document.body,{childList:true,subtree:true});
})();

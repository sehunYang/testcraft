'use strict';
// Navigation belongs to each card; artwork and approval remain in the saved exam.
const imageFlowStates=new Map();
const imageFlowSteps=['제작 계획','그림 생성','그림·글씨 편집','최종 확인'];
function imageFlowState(){
 const c=current(),key=state.exam.id+':'+c.id;
 if(!imageFlowStates.has(key))imageFlowStates.set(key,{step:c.image?.approved?3:c.image?2:c.image_plan_approval?1:0,file:c.image?.file||null,feedback:''});
 const flow=imageFlowStates.get(key);
 if(flow.step===1&&c.image?.file&&flow.file!==c.image.file&&state.job?.status!=='running')flow.step=2;
 if(state.job?.status!=='running')flow.file=c.image?.file||null;
 if(flow.step>1&&!c.image)flow.step=0;
 if(flow.step===1&&(!state.exam.card_approval||!c.image_plan_approval))flow.step=0;
 return flow;
}
function imageFlowAllowed(step){return Number.isInteger(step)&&step>=0&&step<=3&&(step===0||step===1&&!!state.exam.card_approval&&!!current().image_plan_approval||step>=2&&!!current().image)}
function imageFlowButton(step,text,primary=false){return `<button data-image-step="${step}" class="${primary?'primary':'secondary'}" ${!imageFlowAllowed(step)?'disabled':''}>${text}</button>`}
function imageFlowEditor(){const c=current();return `${vectorToolbar()}<div class="layer-toolbar">${Object.entries(labelKindNames).map(([k,l])=>`<button class="small-btn" data-add-label="${k}">＋ ${l}</button>`).join('')}<button class="small-btn" data-layer-action="labels" ${!c.image_plan_approval||!state.exam.card_approval?'disabled':''}>글씨 프롬프트 추가 적용</button><button class="small-btn" data-layer-action="empty" ${c.image_labels?.length?'disabled':''}>글씨 없이 완료</button></div><div class="layer-canvas-wrap"><svg id="layerCanvas" viewBox="0 0 1000 640" tabindex="0" role="application" aria-label="자료 그림 객체 편집. 도형과 글씨를 선택하여 이동하고 손잡이로 크기를 조절합니다."></svg></div><div id="vectorProperties"></div><div id="labelProperties"></div><div class="buttons-wrap section-title">${imageFlowButton(1,'← 배경 다시 만들기')}<button id="saveLabels" class="secondary">그림·글씨 편집 저장</button>${imageFlowButton(3,'저장하고 최종 확인 →',true)}</div>`}
function imageEditor(){
 if(current().data_kind!=='image')return `<div class="image-work layers-work image-flow">${rail(true)}<section class="panel"><div class="panel-body"><h3>이 문항은 자료 그림을 사용하지 않습니다</h3><p class="flow-copy">왼쪽에서 자료 그림이 있는 문항을 선택하세요. 이 문항에 그림이 필요하면 문항 작성에서 자료 유형을 변경할 수 있습니다.</p><button data-stage="1" class="secondary">문항 작성으로 이동</button></div></section></div>`;
 const c=current(),im=c.image,flow=imageFlowState(),step=flow.step;
 const descriptions=['정확히 고정할 그림 요소와 별도로 넣을 글씨를 정합니다.','확인한 제작 계획으로 글씨 없는 배경을 만들고, 글씨를 자동 배치합니다.','그림 객체와 글씨를 각각 다듬습니다. 배경을 다시 만들어도 글씨는 유지됩니다.','완성된 그림과 글씨를 함께 확인한 뒤 시험지에 넣을 그림을 확정합니다.'];
 let body='';
 if(step===0)body=`${!state.exam.card_approval?'<div class="flow-notice">제작 계획을 검토한 뒤 문항카드 전체 승인을 완료해 주세요. 실제 그림 생성은 승인 이후에 진행됩니다.</div>':''}${imagePlanFields(c)}<div class="flow-footer"><span>그림 안에 글씨를 생성하지 않습니다. 글씨는 독립 객체로 배치합니다.</span><button id="confirmImagePlan" class="primary" ${!state.exam.card_approval?'disabled':''}>${c.image_plan_approval?'제작 계획 확인 · 다음 →':'제작 계획 확정 · 다음 →'}</button></div>`;
 if(step===1)body=`<div class="flow-generation"><div><div class="flow-summary"><span class="badge">${esc(c.image_mode)}</span><b>제작 계획 확인 완료</b><p>배경 그림 생성 → 물리량·수식·한글 자동 배치</p></div>${im?`<label>배경 그림 수정 요청<textarea id="feedback" placeholder="바꿀 그림 요소를 적어 주세요. 기존 글씨 위치와 내용은 유지됩니다.">${esc(flow.feedback)}</textarea></label>`:'<p class="flow-copy">그림은 글씨 없이 만들고, 입력한 글씨 프롬프트를 별도 객체로 배치합니다. 완료되면 편집 단계로 이동합니다.</p>'}<button id="generateImage" class="primary wide">${im?'배경 그림 다시 생성':'그림 생성 시작'}</button><details class="flow-import"><summary>이미 준비한 그림이 있나요?</summary><p class="hint">글씨 없는 그림을 가져온 뒤 다음 단계에서 글씨를 추가할 수 있습니다.</p><div class="buttons-wrap"><button id="uploadImage">그림 업로드</button><button id="openLibrary">기존 그림 선택</button></div></details></div><div class="flow-generation-preview">${im?`<img src="/assets/${state.exam.id}/${im.file}" alt="현재 배경 그림"><span>현재 배경 · 글씨 레이어는 별도로 유지됩니다.</span>`:'<div class="flow-placeholder"><img src="/icons/studio.svg" alt="" width="56" height="56"><b>그림을 만들 준비가 됐습니다</b><span>완료된 배경을 이곳에서 확인할 수 있습니다.</span></div>'}</div></div><div class="flow-footer">${imageFlowButton(0,'← 제작 계획')}${imageFlowButton(2,'현재 그림 편집 →')}</div>`;
 if(step===2)body=imageFlowEditor();
 if(step===3){const ready=state.exam.card_approval&&c.image_plan_approval&&c.labels_initialized;body=`<div class="flow-review"><div class="flow-review-art"><svg id="imageReviewCanvas" viewBox="0 0 1000 640" role="img" aria-label="그림과 글씨 최종 미리보기"></svg><p id="imageReviewStatus" role="status"></p></div><aside class="flow-review-checks"><h3>${im.approved?'✓ 최종 확정 완료':'시험지에 넣기 전 확인하세요'}</h3><ul><li>그림의 값·비례·방향이 문항과 맞나요?</li><li>물리량·수식·한글의 내용과 위치가 맞나요?</li><li>글씨가 그림을 가리거나 잘리지 않나요?</li></ul>${im.edit_notice?`<p class="hint">${esc(im.edit_notice)}</p>`:''}${!ready?'<div class="flow-notice">문항카드 승인, 제작 계획 확인, 글씨 배치를 완료해 주세요. 글씨가 필요 없으면 편집 단계에서 ‘글씨 없이 완료’를 선택하세요.</div>':''}${im.note||im.checks?.length?`<details><summary>생성·검산 기록</summary><p>${esc(im.note||'')}</p>${(im.checks||[]).map(x=>`<p class="check-result ${x.ok?'':'fail'}">${esc(x.label)} · ${x.ok?'등식 일치':'확인 필요'}</p>`).join('')}</details>`:''}<button id="approveImage" class="primary wide" ${!ready?'disabled':''}>${im.approved?'최종 확정 해제':'그림 + 글씨 최종 확정'}</button>${im.approved?`<a class="flow-download" href="/assets/${state.exam.id}/${im.final_file}" download>확정 PNG 다운로드 ↗</a>`:''}</aside></div><div class="flow-footer">${imageFlowButton(2,'← 편집으로 돌아가기')}${im.approved?'<button class="primary" data-image-next-card>다음 자료 그림 →</button>':'<span>최종 확정한 그림이 시험지에 들어갑니다.</span>'}</div>`}
 return `<div class="image-work layers-work image-flow" data-image-flow-step="${step}">${rail(true)}<div class="image-flow-main"><nav class="image-flow-steps" aria-label="자료 그림 제작 단계">${imageFlowSteps.map((name,i)=>`<button data-image-step="${i}" ${i===step?'aria-current="step"':''} ${!imageFlowAllowed(i)?'disabled':''}><span>${i+1}</span><b>${name}</b></button>`).join('')}</nav><section class="panel flow-panel"><div class="panel-head"><div><small>자료 그림 ${c.no}번 · ${step+1} / 4</small><h3 id="imageFlowHeading" tabindex="-1">${imageFlowSteps[step]}</h3><p>${descriptions[step]}</p></div><span class="badge ${im?.approved?'success':'dim'}">${im?.approved?'확정 완료':step===0?'계획 확인':step===1?'생성 준비':'편집 중'}</span></div><div class="panel-body">${body}</div></section></div></div>`;
};
function imageFlowPreview(){
 const canvas=$('#imageReviewCanvas');if(!canvas)return;
 const c=current(),im=c.image,labels=(c.image_labels||[]).filter(o=>o.visible!==false);
 canvas.innerHTML=`<rect width="1000" height="640" fill="white"/>${scene()?vectorMarkup():`<image href="/assets/${state.exam.id}/${im.file}" width="1000" height="640" preserveAspectRatio="none"/>`}${labels.map(o=>{const g=glyphCache.get(glyphKey(o));return g?`<g transform="translate(${o.x} ${o.y}) rotate(${o.rotation} ${g.width/2} ${g.height/2})"><image href="${g.url}" width="${g.width}" height="${g.height}"/></g>`:''}).join('')}`;
 const missing=labels.filter(o=>!glyphCache.has(glyphKey(o))),failed=missing.some(o=>glyphErrors.has(glyphKey(o)));
 $('#imageReviewStatus').textContent=failed?'글씨를 표시하지 못했습니다. 편집 단계에서 내용을 확인해 주세요.':missing.length?'글씨 미리보기를 준비하고 있습니다…':'그림과 글씨가 합쳐진 모습입니다.';
 const button=$('#approveImage');if(button&&!im.approved)button.disabled=state.job?.status==='running'||!!missing.length||!state.exam.card_approval||!c.image_plan_approval||!c.labels_initialized;
 for(const o of missing)loadGlyph(o);
}
const imageFlowDraw=drawLayers;
drawLayers=function(){imageFlowDraw();imageFlowPreview()};
function initImageFlow(){
 if(!$('.image-flow'))return;
 if(current().data_kind!=='image')return;
 const step=imageFlowState().step;
 if(step===0){
  const notice=$('.flow-panel .flow-notice');if(notice)notice.id='imageFlowApprovalNotice';
  else{const node=document.createElement('div');node.id='imageFlowApprovalNotice';node.className='flow-notice';node.hidden=true;$('.flow-panel>.panel-body').prepend(node)}
 }
 if(step===2&&!current().labels_initialized){
  const notice=document.createElement('div');notice.id='imageFlowRecovery';notice.className='flow-notice';
  const ready=state.exam.card_approval&&current().image_plan_approval;
  notice.innerHTML=`<b>배경은 저장됐습니다. 글씨 배치를 완료해 주세요.</b><p>글씨를 자동 배치하거나 직접 추가할 수 있습니다. 배경을 다시 생성할 필요는 없습니다.</p><div class="buttons-wrap"><button data-image-retry-labels ${ready?'':'disabled'}>글씨만 자동 배치</button><button data-image-no-labels ${current().image_labels?.length?'disabled':''}>글씨 없이 진행</button></div>${ready?'':'<p>자동 배치 전에 제작 계획과 문항카드 승인을 확인해 주세요.</p>'}`;
  $('#designerPreparation').before(notice);
 }
 if(step===1){
  const job=state.job,block=typeof uxActiveImageBlock==='function'?uxActiveImageBlock(state.exam.cards[state.card]):null,failed=job?.exam_id===state.exam.id&&job?.failed?.find(item=>item.id===current().id&&(!item.material_id||item.material_id===block?.id));
  if(failed&&job.status!=='running'){
   const notice=document.createElement('div');notice.className='flow-notice';notice.setAttribute('role','status');notice.innerHTML=`<b>그림 생성을 완료하지 못했습니다.</b><p>${esc(failed.error)}</p><p>요청 내용을 확인하고 아래 생성 버튼으로 다시 시도하세요.</p>`;$('.flow-generation').before(notice);
  }
 }
 const preparation=$('#designerPreparation>summary');if(preparation)preparation.textContent='그림 객체 변환 · 기본 도형 · 글씨 배치 설정';
 const confirm=$('#confirmImagePlan');if(confirm)confirm.onclick=()=>action(async()=>{await save();state.exam=await api('/api/confirm-image-plan',{exam_id:state.exam.id,card_id:current().id});const c=current();imageFlowState().step=c.image?(c.image.approved||c.labels_initialized?3:2):1;render();$('#imageFlowHeading')?.focus({preventScroll:true})});
 const fields=$('.image-flow .image-plan-fields');if(fields){
  const nodes=[...fields.children],divider=nodes.findIndex(n=>n.classList.contains('sep'));
  const drawing=document.createElement('div'),writing=document.createElement('div');drawing.className=writing.className='flow-plan-column';
  drawing.innerHTML='<h3>그림 제작 규칙</h3>';drawing.append(...nodes.slice(0,divider));writing.append(...nodes.slice(divider+1));fields.replaceChildren(drawing,writing);
 }
 imageFlowPreview();
}
document.addEventListener('input',e=>{
 if(!$('.image-flow'))return;
 if(e.target.id==='feedback')imageFlowState().feedback=e.target.value;
 if(e.target.dataset.field){
  document.querySelectorAll('[data-image-step]').forEach(button=>button.disabled=!imageFlowAllowed(Number(button.dataset.imageStep)));
  const notice=$('#imageFlowApprovalNotice');if(notice&&!state.exam.card_approval){notice.hidden=false;notice.innerHTML='제작 계획이 변경되어 문항카드 승인이 해제되었습니다. 문항 검토와 전체 승인을 다시 완료해 주세요. <button class="small-btn" data-stage="1">문항 검토로 이동</button>'}
 }
});
document.addEventListener('click',e=>{
 if(e.target.closest('[data-image-retry-labels]')){$('#designerPreparation [data-layer-action="labels"]')?.click();return}
 if(e.target.closest('[data-image-no-labels]')){$('#designerPreparation [data-layer-action="empty"]')?.click();return}
 const btn=e.target.closest('[data-image-step],[data-image-next-card]');if(!btn)return;
 action(async()=>{
  if(state.job?.status==='running')return;
  await save();
  if(btn.hasAttribute('data-image-next-card')){const cards=state.exam.cards;let next=-1;for(let n=1;n<cards.length;n++){const i=(state.card+n)%cards.length;if(cards[i].data_kind==='image'&&!cards[i].image?.approved){next=i;break}}if(next<0){state.stage=3;render();toast('자료 그림을 모두 확인했습니다. 검토·출력에서 시험지를 완성하세요.');return}state.card=next}
  else{const step=Number(btn.dataset.imageStep);if(!imageFlowAllowed(step))return;imageFlowState().step=step}
  ve.expanded=false;render();$('#imageFlowHeading')?.focus({preventScroll:true});$('.image-flow-steps')?.scrollIntoView({block:'start',behavior:'instant'});
 });
});

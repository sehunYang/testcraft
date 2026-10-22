'use strict';
// HML stays on the server; users receive native Hancom HWPX documents.
(() => {
 const pair=['시험지_학생용.hwpx','시험지_교사용.hwpx'];
 let busy=false;
 const ready=b=>!!b&&pair.every(name=>b.files?.includes(name))&&(!b.conversion?.status||b.conversion.status==='ready');
 const files=b=>(b?.files||[]).filter(name=>!name.toLowerCase().endsWith('.hml')&&(!name.toLowerCase().endsWith('.hwpx')||ready(b))&&(name!=='출제결과.zip'||ready(b)));
 const message=b=>b?.conversion?.message||'HWPX 시험지로 변환해야 다운로드를 마칠 수 있습니다.';
 const download=(e,b,name,label)=>`<a class="download ux-download" href="/download/${e.id}/${b.id}/${encodeURIComponent(name)}" download><span>${esc(label||name)}</span><small>${esc(name.split('.').pop().toUpperCase())}</small></a>`;
 const retry=(b,primary=false)=>state.boot?.hwp_conversion_available?
  `<button class="${primary?'primary':'small-btn'}" data-recalc="${esc(b.id)}">${b.conversion?.status==='failed'?'HWPX 다시 만들기':'HWPX 변환'}</button>`:
  `<button class="${primary?'primary':'small-btn'}" data-hwpx-action="check">한글 연결 확인</button>`;
 const note=b=>`<p class="notice warn" role="status">${esc(message(b))}${!state.boot?.hwp_conversion_available?' Windows용 한컴오피스 한글을 설치한 뒤 연결을 확인해 주세요.':''}</p>`;
 const originalPrimary=typeof uxPrimary==='function'?uxPrimary:null;
 function primary(){
  const e=state.exam,latest=e?.exports?.at(-1),fresh=latest&&latest.content_digest===e.content_digest;
  if(!e||state.stage!==3)return originalPrimary?originalPrimary():'';
  if(originalPrimary&&((typeof uxState!=='undefined'&&(uxState.conflict||uxState.status==='failed'))||state.job?.status==='running'))return originalPrimary();
  if(fresh&&ready(latest))return `<div class="task-action"><span>학생용·교사용 HWPX와 정답·해설이 준비됐습니다.</span><a class="primary action-link" href="/download/${e.id}/${latest.id}/${encodeURIComponent('출제결과.zip')}" download>전체 받기</a></div>`;
  if(fresh)return `<div class="task-action"><span>${esc(message(latest))}</span>${retry(latest,true)}</div>`;
  if(!e.validation?.ready)return originalPrimary?originalPrimary():`<div class="task-action"><span>${esc(e.validation?.errors?.[0]||'출력 전 검토를 완료해 주세요.')}</span><button id="refreshValidation">검토 상태 확인</button></div>`;
  if(!state.boot?.hwp_conversion_available)return '<div class="task-action"><span>HWPX 출력을 위해 이 PC에 설치된 한글을 연결해 주세요.</span><button class="primary" data-hwpx-action="check">한글 연결 확인</button></div>';
  return '<div class="task-action"><span>한글에서 수식을 재계산한 뒤 학생용·교사용 HWPX를 저장합니다.</span><button class="primary" data-hwpx-action="create">시험지 만들기</button></div>';
 }
 if(originalPrimary)uxPrimary=primary;
 exportsView=function(){
  const e=state.exam,v=e.validation||{ready:false,errors:[],issues:[],warnings:[]},latest=e.exports?.at(-1),fresh=latest&&latest.content_digest===e.content_digest;
  const issues=(v.issues||[]).map(item=>{
   if(typeof uxIssueActionLabel!=='function')return `<li>${esc(item.message)}</li>`;
   const c=e.cards.find(c=>c.id===item.card_id),label=typeof uxIssueMaterialLabel==='function'?uxIssueMaterialLabel(item):'';
   return `<li><button class="issue-link" data-issue-code="${esc(item.code)}" data-issue-card="${esc(item.card_id||'')}" data-issue-material="${esc(item.material_id||'')}" data-issue-field="${esc(item.field||'')}" data-issue-stage="${esc(item.stage||'review')}"><b>${esc(c?`${c.no}번${label?' · '+label:''}`:item.message)}</b><span>${esc(item.message)}</span><em>${esc(uxIssueActionLabel(item))}</em></button></li>`;
  }).join('');
  const main=latest?[...pair,'정답과해설.md'].filter(name=>files(latest).includes(name)):[];
  const other=latest?files(latest).filter(name=>!main.includes(name)&&name!=='출제결과.zip'):[];
  const history=(e.exports||[]).slice(0,-1).reverse();
  return `<div class="export-layout ux-export-layout"><section class="panel"><div class="panel-head"><div><h2>받을 파일을 준비합니다</h2><p>${e.cards.length}문항 · ${Number(e.cards.reduce((sum,c)=>sum+Number(c.points||0),0).toFixed(2))}점</p></div><span class="badge ${v.ready?'success':'warn'}">${v.ready?'출력 검사 통과':`${v.issues?.length||v.errors?.length||1}개 확인 필요`}</span></div><div class="panel-body">${issues?`<div class="issue-panel"><h3>해결할 항목</h3><ul class="issues">${issues}</ul></div>`:v.ready?'<div class="notice">문항·배점·승인과 그림 확인을 통과했습니다.</div>':`<div class="notice warn">${esc(v.errors?.join(' / ')||'검토 상태를 확인해 주세요.')}</div>`}${(v.warnings||[]).map(text=>`<div class="notice warn">${esc(text)}</div>`).join('')}${latest?`<section class="latest-export"><div><h3>최근 출력 · ${ready(latest)?fresh?'최신':'문항 내용 수정 전':'HWPX 변환 필요'}</h3><p>${fresh?'현재 출제 내용으로 만든 출력본입니다.':'현재 내용과 다른 출력본입니다. 다시 만들어 최신 상태를 반영하세요.'}</p></div>${!ready(latest)||latest.conversion?.retry_error?note(latest):''}<div class="priority-files">${main.map(name=>download(e,latest,name)).join('')}${ready(latest)&&latest.files.includes('출제결과.zip')?download(e,latest,'출제결과.zip','전체 받기'):''}${!fresh&&!ready(latest)?retry(latest):''}</div>${other.length?`<details class="other-files"><summary>기타 파일 ${other.length}개</summary>${other.map(name=>download(e,latest,name)).join('')}</details>`:''}${!fresh?'<p class="outdated-notice">현재 내용과 다른 출력본 · 이전 파일은 그대로 보존됩니다.</p>':''}</section>`:'<div class="placeholder">출력 전 점검이 끝나면 학생용·교사용 HWPX와 정답·해설을 만들 수 있습니다.</div>'}<p class="print-note">앱이 별도의 한글 창을 숨겨 변환합니다. 최종 인쇄 배치는 HWPX를 열어 확인해 주세요.</p><div class="review-action-dock" id="taskActionBar">${primary()}</div></div></section><aside class="panel export-history"><div class="panel-head"><h3>이전 버전 <span class="muted">${history.length}</span></h3></div><div class="panel-body">${history.map(b=>`<details class="export-version"><summary>${esc(b.created.replace('T',' '))} · ${b.content_digest===e.content_digest?'현재 내용':'문항 내용 '+b.revision+' 버전'}</summary>${!ready(b)||b.conversion?.retry_error?note(b):''}${files(b).map(name=>download(e,b,name,name==='출제결과.zip'?'전체 받기':undefined)).join('')}${!ready(b)?retry(b):''}</details>`).join('')||'<p class="hint">새 출력본을 만들면 이전 버전이 이곳에 보존됩니다.</p>'}</div></aside></div>`;
 };
 function progress(){
  let dialog=document.querySelector('#hwpxProgressDialog');
  if(dialog)return dialog;
  dialog=document.createElement('dialog');dialog.id='hwpxProgressDialog';dialog.className='job-progress-dialog';
  dialog.setAttribute('aria-labelledby','hwpxProgressTitle');dialog.setAttribute('aria-describedby','hwpxProgressMessage');
  dialog.innerHTML='<div class="job-progress-heading"><span class="job-progress-spinner" aria-hidden="true"></span><h2 id="hwpxProgressTitle">HWPX 시험지를 만들고 있습니다</h2></div><p id="hwpxProgressMessage" class="job-progress-message" role="status">한글에서 학생용·교사용 문서를 열어 수식을 재계산하고 저장합니다. 잠시 기다려 주세요.</p>';
  dialog.addEventListener('cancel',event=>event.preventDefault());document.body.append(dialog);return dialog;
 }
 async function execute(bundleId){
  if(busy)return;busy=true;const dialog=progress();
  try{
   dialog.showModal();await save();
   const result=await api(bundleId?'/api/recalculate':'/api/export',{exam_id:state.exam.id,...(bundleId?{export_id:bundleId}:{})});
   state.exam=result;state.dirty=false;
   if(typeof uxBaseExam!=='undefined')uxBaseExam.value=uxClone(result);
   render();const b=bundleId?result.exports.find(b=>b.id===bundleId):result.exports.at(-1);
   toast(ready(b)&&!b.conversion?.retry_error?'학생용·교사용 HWPX를 만들었습니다.':message(b));
  }finally{if(dialog.open)dialog.close();busy=false;}
 }
 window.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  const type=button.dataset.hwpxAction;
  if(!type&&!button.hasAttribute('data-recalc')&&button.id!=='exportBtn'&&button.dataset.uxAction!=='create-export')return;
  event.preventDefault();event.stopImmediatePropagation();
  action(async()=>{
   if(type==='check'){
    state.boot=await api('/api/bootstrap');render();
    toast(state.boot.hwp_conversion_available?'한글이 연결됐습니다. HWPX 시험지를 만들 수 있습니다.':'한글을 찾지 못했습니다. Windows용 한컴오피스 한글 설치를 확인해 주세요.');return;
   }
   await execute(button.hasAttribute('data-recalc')?button.dataset.recalc:null);
  });
 },true);
})();

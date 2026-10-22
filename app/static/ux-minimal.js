'use strict';
// Focused navigation, conditionally visible authoring, and a revision-safe draft queue.
const uxClone=value=>value==null?value:JSON.parse(JSON.stringify(value));
const uxBaseExam={value:null};
const uxState={version:0,queue:Promise.resolve(),savePromise:null,timer:null,draftTimer:null,status:'saved',conflict:null,tab:'question',restoring:false,bulkExamId:null,bulkImageIds:new Set(),duplicateRequestIds:new Map(),duplicateInFlight:new Set(),deleteReturnFocus:null};
uxState.materialByCard=Object.create(null);
const uxStatsUi={examId:null,standardsExpanded:false,helpExpanded:false,resizeObserver:null,measureFrame:0};
function uxStatsFitStandardPreview(target){
 const preview=target?.querySelector('.standard-preview');if(!preview)return;
 const codes=[...preview.querySelectorAll('.standard-preview-code')],more=preview.querySelector('.standard-more-count');
 if(!more)return;
 codes.forEach(code=>code.hidden=false);
 const widths=codes.map(code=>code.getBoundingClientRect().width),gap=parseFloat(getComputedStyle(preview).columnGap)||0,available=preview.clientWidth;
 let visible=codes.length;
 while(visible>0){
  const remaining=codes.length-visible;more.textContent=remaining?`+${remaining}`:'';more.hidden=remaining===0;
  const used=widths.slice(0,visible).reduce((sum,width)=>sum+width,0)+Math.max(0,visible-1)*gap+(remaining?gap+more.getBoundingClientRect().width:0);
  if(used<=available)break;
  visible--;
 }
 codes.forEach((code,index)=>{code.hidden=index>=visible});
 const remaining=codes.length-visible;more.textContent=remaining?`+${remaining}`:'';more.hidden=remaining===0;
}
function uxStatsMeasureHeight(){
 if(uxStatsUi.measureFrame)cancelAnimationFrame(uxStatsUi.measureFrame);
 uxStatsUi.measureFrame=requestAnimationFrame(()=>{
  uxStatsUi.measureFrame=0;
  const live=$('#liveStats'),secondary=$('#secondaryStats');
  const visible=state.exam&&state.stage<2?live:state.exam?secondary:null;
  uxStatsFitStandardPreview(state.exam&&state.stage<2?live:state.exam?$('#secondaryStatsBody'):null);
  const height=visible&&!visible.hidden?Math.ceil(visible.getBoundingClientRect().height):0;
  document.documentElement.style.setProperty('--stats-height',`${height}px`);
 });
}
function uxStatsObserveSize(){
 if(!uxStatsUi.resizeObserver&&typeof ResizeObserver==='function'){
  uxStatsUi.resizeObserver=new ResizeObserver(uxStatsMeasureHeight);
  const live=$('#liveStats'),secondary=$('#secondaryStats');
  if(live)uxStatsUi.resizeObserver.observe(live);
  if(secondary){uxStatsUi.resizeObserver.observe(secondary);secondary.addEventListener('toggle',uxStatsMeasureHeight)}
 }
 uxStatsMeasureHeight();
}
window.addEventListener('resize',uxStatsMeasureHeight,{passive:true});
const uxMaterialImageFields=['image_mode','image_locked','image_creative','image_text_physics','image_text_math','image_text_korean','image_text_none','image_plan_version','image_plan_approval','image_labels','labels_initialized','image_scene','image'];
const uxImageRequestPaths=new Set(['/api/confirm-image-plan','/api/image','/api/vectorize']);
function uxMakeId(){return crypto.randomUUID().replaceAll('-','').slice(0,16)}
function uxLegacyMaterial(card){
 if(!card||card.data_kind==='none'||!card.data_kind)return null;
 return {id:card.id,kind:card.data_kind==='image'?'image':card.data_kind,label:'',content:card.material||'',...Object.fromEntries(uxMaterialImageFields.map(key=>[key,card[key]]))};
}
function uxVisibleMaterials(card){return Array.isArray(card?.materials)?card.materials:(uxLegacyMaterial(card)?[uxLegacyMaterial(card)]:[])}
function uxImageMaterials(card){return uxVisibleMaterials(card).filter(block=>block.kind==='image')}
function uxSyncMaterialAliases(card){
 if(!card||!Array.isArray(card.materials))return;
 const blocks=card.materials,firstImage=blocks.find(block=>block.kind==='image'),firstContent=blocks[0];
 card.data_kind=firstImage?'image':firstContent?.kind||'none';
 card.material=firstContent?.content||'';
 if(firstImage){for(const key of uxMaterialImageFields)if(key in firstImage)card[key]=uxClone(firstImage[key])}
 else{for(const [key,value] of Object.entries(uxImageDefaults()))card[key]=uxClone(value)}
}
function uxEnsureMaterials(card){
 if(Array.isArray(card.materials))return card.materials;
 const legacy=uxLegacyMaterial(card);
 if(legacy?.kind==='image'&&!legacy.label)legacy.label='(가)';
 card.materials=legacy?[legacy]:[];
 return card.materials;
}
function uxActiveBlock(card,preferImage=false){
 if(!card)return null;
 const blocks=uxVisibleMaterials(card);if(!blocks.length)return null;
 const selected=uxState.materialByCard?.[card.id];
 let block=blocks.find(item=>item.id===selected);
 if(preferImage&&block?.kind!=='image')block=null;
 if(!block)block=preferImage?(blocks.find(item=>item.kind==='image'&&!item.image?.approved)||blocks.find(item=>item.kind==='image')):blocks[0];
 if(block)uxState.materialByCard[card.id]=block.id;
 return block||null;
}
function uxActiveImageBlock(card){return uxActiveBlock(card,true)}
const uxImageToolStates=new Map(),uxLabelSelections=new Map();
function uxImageToolKey(card=state.exam?.cards?.[state.card],block=uxActiveImageBlock(card)){
 if(!card||!block)return null;return `${state.exam.id}:${card.id}:${block.id}:${block.image?.sha256||block.image?.file||''}`;
}
function uxStoreImageToolState(card=state.exam?.cards?.[state.card],block=uxActiveImageBlock(card)){
 if(typeof ve==='undefined'||!ve)return;
 const key=uxImageToolKey(card,block);if(!key)return;
 if(typeof uxImageToolKey==='function'&&ve.key!==key)return;
 const history=typeof designer!=='undefined'?designer.history:null;
 uxImageToolStates.set(key,{selected:[...ve.selected],designLabels:history&&designer.labels?[...designer.labels]:[],history:history?{undoStack:history.undoStack.slice(),undoStackPointer:history.undoStackPointer}:null,past:[...ve.past],future:[...ve.future],zoom:ve.zoom,grid:ve.grid,snap:ve.snap,aspect:ve.aspect,expanded:ve.expanded});
 if(typeof selectedLabel!=='undefined')uxLabelSelections.set(key,selectedLabel);
}
function uxRestoreImageToolState(key,tools=ve){
 if(!key||!tools)return;const saved=uxImageToolStates.get(key);
 if(typeof designer!=='undefined'&&designer.history){
  if(saved?.history){designer.history.undoStack=saved.history.undoStack.slice();designer.history.undoStackPointer=saved.history.undoStackPointer;designer.labels=new Set(saved.designLabels||[])}
  else{designer.history.resetUndoStack();designer.labels.clear()}
 }
 if(!saved){if(typeof selectedLabel!=='undefined')selectedLabel=null;return}
 tools.selected=new Set(saved.selected||[]);tools.past=[...(saved.past||[])];tools.future=[...(saved.future||[])];
 for(const keyName of ['zoom','grid','snap','aspect','expanded'])if(keyName in saved)tools[keyName]=saved[keyName];
 if(typeof selectedLabel!=='undefined')selectedLabel=uxLabelSelections.get(key)||null;
}
function uxClearMaterialTools(card=state.exam?.cards?.[state.card]){
 uxStoreImageToolState(card);
 if(typeof ve!=='undefined'&&ve){ve.key=null;ve.selected?.clear?.();ve.past=[];ve.future=[];ve.drag=null;ve.expanded=false}
 if(typeof designer!=='undefined'&&designer){designer.labels.clear();designer.history.resetUndoStack()}
 if(typeof selectedLabel!=='undefined')selectedLabel=null;
 if(typeof layerDrag!=='undefined')layerDrag=null;if(typeof labelTimer!=='undefined')clearTimeout(labelTimer);
}
function uxSelectMaterial(card,id,{renderNow=false,preferImage=false}={}){
 const block=uxVisibleMaterials(card).find(item=>item.id===id&&(!preferImage||item.kind==='image'));if(!block)return false;
 uxClearMaterialTools(card);uxState.materialByCard[card.id]=block.id;
 if(renderNow)render();return true;
}
const uxBaseCurrent=current;
current=function(){
 const card=uxBaseCurrent();if(!card)return card;
 return new Proxy(card,{
  get(target,key,receiver){
   if(key==='data_kind'&&Array.isArray(target.materials)){const images=target.materials.find(block=>block.kind==='image');return images?'image':target.materials[0]?.kind||'none'}
   if(key==='material'&&Array.isArray(target.materials)){const block=uxActiveBlock(target,state.stage===2||state.stage===1&&uxState.tab==='plan');return block?.content??target.material??''}
   if(uxMaterialImageFields.includes(key)&&Array.isArray(target.materials)){
    const block=uxActiveImageBlock(target);if(block&&key in block)return block[key];
   }
   return Reflect.get(target,key,receiver);
  },
  set(target,key,value,receiver){
   if(key==='material'&&Array.isArray(target.materials)){
    const block=uxActiveBlock(target,state.stage===2||state.stage===1&&uxState.tab==='plan');if(block){block.content=value;uxSyncMaterialAliases(target);return true}
   }
   if(uxMaterialImageFields.includes(key)&&Array.isArray(target.materials)){
    const block=uxActiveImageBlock(target);if(block){block[key]=value;uxSyncMaterialAliases(target);return true}
   }
   return Reflect.set(target,key,value,receiver);
  }
 });
};
const uxBaseApi=api;
api=function(path,data){
 const payload=data?{...data}:data;
 const block=state.exam&&uxActiveImageBlock(state.exam.cards?.[state.card]);
 const imageJob=path==='/api/jobs'&&['image','plan','labels'].includes(payload?.action);
 const imageApproval=path==='/api/approve'&&payload?.kind==='image';
 if(block&&payload?.exam_id===state.exam?.id&&payload.card_id===state.exam.cards?.[state.card]?.id&&!payload.material_id&&(uxImageRequestPaths.has(path)||imageApproval||imageJob))payload.material_id=block.id;
 return uxBaseApi(path,payload);
};
const uxBaseImageFlowState=imageFlowState;
imageFlowState=function(){
 const c=current(),block=uxActiveImageBlock(state.exam?.cards?.[state.card]);if(!c||!block)return uxBaseImageFlowState();
 const key=`${state.exam.id}:${c.id}:${block.id}`;
 if(!imageFlowStates.has(key))imageFlowStates.set(key,{step:block.image_plan_approval?(block.image?.approved?3:block.image?block.labels_initialized?3:2:1):0,file:block.image?.file||null,feedback:''});
 const flow=imageFlowStates.get(key);
 if(!block.image_plan_approval&&flow.step!==0)flow.step=0;
 if(flow.step===1&&block.image?.file&&flow.file!==block.image.file&&state.job?.status!=='running')flow.step=block.labels_initialized?3:2;
 if(state.job?.status!=='running')flow.file=block.image?.file||null;
 if(flow.step>1&&!block.image)flow.step=block.image_plan_approval?1:0;
 if(flow.step===1&&(!state.exam.card_approval||!block.image_plan_approval))flow.step=0;
 return flow;
};
labels.splice(0,labels.length,'설계','검토','그림','출력');
function uxDraftKey(id){return `qm-draft:${id}`}
function uxLocationKey(id){return `qm-location:${id}`}
function uxReadDraft(id){let raw=null;try{raw=localStorage.getItem(uxDraftKey(id));if(!raw)return null;const value=JSON.parse(raw),cards=value?.local?.cards;const valid=value?.exam_id===id&&value.local?.id===id&&Array.isArray(cards)&&cards.length>=1&&cards.length<=100&&cards.every(c=>typeof c?.id==='string'&&c.id.length>0)&&new Set(cards.map(c=>c.id)).size===cards.length&&Number.isFinite(Number(value.base_revision))&&Number.isInteger(Number(value.stage))&&Number(value.stage)>=0&&Number(value.stage)<=3&&['question','answer','plan'].includes(value.tab);return valid?value:{_invalidRaw:raw}}catch{return raw?{_invalidRaw:raw}:null}}
function uxWriteDraft(){
 if(!state.exam)return;
 const record={exam_id:state.exam.id,base_revision:uxBaseExam.value?.revision??state.exam.revision,
  base:uxClone(uxBaseExam.value),local:uxClone(state.exam),version:uxState.version,
  stage:state.stage,card_id:current()?.id||null,material_id:uxState.materialByCard[current()?.id]||uxActiveBlock(state.exam.cards[state.card])?.id||null,tab:uxState.tab,
  image_step:typeof imageFlowState==='function'&&state.exam.cards.length?imageFlowState().step:0};
 try{localStorage.setItem(uxDraftKey(state.exam.id),JSON.stringify(record));return true}catch(e){uxSetSaveStatus('failed');console.warn('Draft storage failed',e);return false}
}
function uxScheduleDraft(){clearTimeout(uxState.draftTimer);uxState.draftTimer=setTimeout(uxWriteDraft,180)}
function uxRemoveDraft(id){try{localStorage.removeItem(uxDraftKey(id))}catch{}}
function uxPersistLocation(){
 if(!state.exam)return;
 const value={stage:state.stage,card_id:current()?.id||null,material_id:uxState.materialByCard[current()?.id]||uxActiveBlock(state.exam.cards[state.card])?.id||null,tab:uxState.tab,
  image_step:typeof imageFlowState==='function'&&state.exam.cards.length?imageFlowState().step:0};
 try{localStorage.setItem(uxLocationKey(state.exam.id),JSON.stringify(value));localStorage.setItem('qm-last-exam',state.exam.id)}catch{}
}
function uxRestoreLocation(exam){
 let value=null;try{value=JSON.parse(localStorage.getItem(uxLocationKey(exam.id))||'null')}catch{}
 if(!value)return;
 state.stage=Math.max(0,Math.min(3,Number(value.stage)||0));
 const card=exam.cards.findIndex(c=>c.id===value.card_id);state.card=card<0?0:card;
 if(value.material_id)uxState.materialByCard[exam.cards[state.card]?.id]=value.material_id;
 uxState.tab=['question','answer','plan'].includes(value.tab)?value.tab:'question';
 if(state.stage>=2&&!exam.card_approval)state.stage=1;
 if(state.stage===2&&typeof imageFlowState==='function'&&value.image_step>=0){const step=Math.max(0,Math.min(3,Number(value.image_step)||0));imageFlowState().step=step}
}
function uxSetSaveStatus(status){
 uxState.status=status;const node=$('#saveState');if(!node)return;
 const labels={dirty:'변경 있음',saving:'저장 중',saved:'저장됨',failed:'저장 실패',conflict:'저장 충돌'};
 node.textContent=labels[status]||'저장됨';node.dataset.status=status;
 uxRefreshPrimary();
}
function api(path,data){
 const payload=data?{...data}:null;
 if(payload?.exam_id&&payload.exam_id===state.exam?.id&&payload.revision===undefined)payload.revision=state.exam.revision;
 return fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':state.boot.token},body:JSON.stringify(payload)}:{}).then(async response=>{
  const value=await response.json();if(!response.ok){const error=new Error(value.error||'요청에 실패했습니다.');Object.assign(error,value,{status:response.status});
   if(value.code==='revision_conflict'&&value.latest&&state.exam?.id===value.latest.id){uxState.conflict={base:uxClone(uxBaseExam.value),local:uxClone(state.exam),remote:uxClone(value.latest)};uxSetSaveStatus('conflict');uxWriteDraft();uxRenderConflict()}
   throw error;
  }return value;
 });
}
function uxMergeServerState(local,saved){
 const result=uxClone(local),byId=new Map((saved.cards||[]).map(c=>[c.id,c]));
 for(const c of result.cards||[]){const remote=byId.get(c.id);if(!remote)continue;
  c.calculation_override=uxClone(remote.calculation_override??null);
  if(Array.isArray(c.materials)&&Array.isArray(remote.materials)){
   const remoteMaterials=new Map(remote.materials.map(block=>[block.id,block]));
   for(const block of c.materials){const server=remoteMaterials.get(block.id);if(!server||block.kind!=='image')continue;
    for(const key of ['image','image_scene','image_labels','labels_initialized'])if(key in server)block[key]=uxClone(server[key]);
    if(block.image_plan_approval&&'image_plan_approval'in server)block.image_plan_approval=uxClone(server.image_plan_approval);
   }
   uxSyncMaterialAliases(c);
  }else{c.image=uxClone(remote.image);if(c.image_plan_approval)c.image_plan_approval=uxClone(remote.image_plan_approval)}
 }
 result.revision=saved.revision;result.updated=saved.updated;
 return result;
}
async function uxDrainSaves(){
 const id=state.exam?.id;if(!id)return state.exam;
 if(uxState.conflict)throw Object.assign(new Error('저장 충돌을 해결한 뒤 계속해 주세요.'),{code:'revision_conflict'});
 clearTimeout(uxState.timer);clearTimeout(uxState.draftTimer);uxWriteDraft();
 try{
  while(state.exam?.id===id&&state.dirty){
   if(uxState.conflict)throw Object.assign(new Error('저장 충돌을 해결한 뒤 계속해 주세요.'),{code:'revision_conflict'});
   const version=uxState.version,snapshot=uxClone(state.exam),data={exam_id:id,revision:snapshot.revision,title:snapshot.title,subject:snapshot.subject,cards:snapshot.cards};
   uxSetSaveStatus('saving');
   const request=uxState.queue.catch(()=>{}).then(()=>api('/api/save',data));uxState.queue=request.catch(()=>{});
   const saved=await request;
   if(state.exam?.id!==id)return state.exam;
   if(version===uxState.version){state.exam=saved;state.dirty=false;uxBaseExam.value=uxClone(saved);uxRemoveDraft(id);uxSetSaveStatus('saved');const notice=$('#saveProblem');if(notice){notice.hidden=true;notice.innerHTML=''}}
   else{
    // Only revision metadata belongs to this older response. Keep every live field,
    // including local approval invalidation and artwork edits, for the next save.
    state.exam.revision=saved.revision;state.exam.updated=saved.updated;
    uxBaseExam.value=uxClone(saved);state.dirty=true;uxSetSaveStatus('dirty');uxWriteDraft();
   }
   uxPersistLocation();
  }
  return state.exam;
 }catch(error){if(error.code==='revision_conflict'){uxSetSaveStatus('conflict');uxWriteDraft()}else uxSetSaveStatus('failed');throw error}
}
function save(){
 if(!state.exam||!state.dirty)return Promise.resolve(state.exam);
 clearTimeout(uxState.timer);
 if(!uxState.savePromise){uxState.savePromise=uxDrainSaves().finally(()=>{uxState.savePromise=null;if(state.exam?.id&&state.dirty&&!uxState.conflict&&uxState.status==='dirty')uxScheduleSave()})}
 return uxState.savePromise;
}
function uxScheduleSave(){if(!state.exam||!state.dirty||uxState.conflict)return;clearTimeout(uxState.timer);uxState.timer=setTimeout(()=>save().catch(uxShowSaveError),800)}
function uxShowSaveError(error){
 if(error?.code==='revision_conflict'){uxRenderConflict();return}
 const holder=$('#saveProblem');if(holder){holder.hidden=false;holder.innerHTML=`<b>저장하지 못했습니다.</b><span>${esc(error?.message||'네트워크 상태를 확인해 주세요.')}</span><button data-ux-retry-save>다시 저장</button><button data-ux-dismiss-save-problem aria-label="저장 오류 닫기">닫기</button>`}
 uxSetSaveStatus('failed');
}
function uxShowInvalidDraft(){const holder=$('#saveProblem');if(holder){holder.hidden=false;holder.innerHTML='<b>초안을 복구하지 못했습니다.</b><span>초안 형식이 올바르지 않아 최신 저장본을 열었습니다. 손상된 원본은 이 브라우저에 따로 보존했습니다.</span><button data-ux-dismiss-save-problem aria-label="초안 안내 닫기">닫기</button>'}}
function markDirty(contentChanged=true){
 if(!state.exam)return;state.dirty=true;uxState.version++;
 if(uxState.conflict)uxState.conflict.local=uxClone(state.exam);
 if(contentChanged&&current()){state.exam.card_approval=null;current().review_approved=false;current().image_plan_approval=null;const im=current().image;if(im&&['stem','material','question','choices','statements','data_kind','image_mode','image_locked','image_creative','image_text_physics','image_text_math','image_text_korean','image_text_none'].includes(uxState.lastField))im.approved=false}
 uxSetSaveStatus('dirty');uxScheduleDraft();uxScheduleSave();
 if(contentChanged){$('#approvalBar').innerHTML=approvalBar();bindApprovalAfterEdit();for(const id of ['generateImage','uploadImage','openLibrary','approveImage','confirmImagePlan']){const el=$('#'+id);if(el)el.disabled=true}}
 renderStats();uxPersistLocation();uxRefreshPrimary();
}
function markLabelDirty(){
 if(!state.exam||!current())return;current().labels_initialized=true;
 if(current().image)current().image.approved=false;
 markDirty(false);
 const button=$('#approveImage');if(button)button.textContent='그림 + 글씨 최종 확정';
}
function vdirty(){
 if(!state.exam||!current())return;
 if(current().image)current().image.approved=false;
 markDirty(false);
 const button=$('#approveImage');if(button)button.textContent='그림 + 글씨 최종 확정';
}
addCard=async function(){
 if(!state.exam)return;authoringOpenChoice();return;
 const c={id:crypto.randomUUID().replaceAll('-','').slice(0,16),no:state.exam.cards.length+1,standard:'',standard_name:'',standard_note:'',type:'',difficulty:'',idea:'',points:'',stem:'',material:'',question:'',statements:'',choices:'',answer:'',concepts:'',explanation:'',review_note:'',data_kind:'none',ai_requested:true,ai_feedback:'',image_mode:'',image_locked:'',image_creative:'',image_text_physics:'',image_text_math:'',image_text_korean:'',image_text_none:false,image_plan_version:2,image_plan_approval:null,image_labels:[],labels_initialized:false,image_scene:null,calculation:false,checks:[],review_approved:false,image:null};
 uxStoreImageToolState();
 state.exam.cards.push(c);state.card=state.exam.cards.length-1;state.stage=0;state.exam.card_approval=null;markDirty(false);await save();render();return c;
};
reorderCards=async function(source,target){
 if(source===target)return;if(state.job?.status==='running')throw Error('생성이 끝난 뒤 순서를 변경해 주세요.');await save();
 const active=current()?.id,from=state.exam.cards.findIndex(c=>c.id===source),to=state.exam.cards.findIndex(c=>c.id===target);if(from<0||to<0)return;
 const cards=state.exam.cards.slice();cards.splice(to,0,cards.splice(from,1)[0]);state.exam.cards=cards.map((c,i)=>({...c,no:i+1}));state.card=state.exam.cards.findIndex(c=>c.id===active);state.exam.card_approval=null;markDirty(false);
 await save();render();toast('문항 순서를 저장하고 번호를 다시 매겼습니다.');
};
function uxOpenExam(id){return action(async()=>{
   await save();uxStoreImageToolState();const remote=await api('/api/exams/'+id);state.exam=remote;state.card=0;state.stage=0;state.dirty=false;state.job=null;uxBaseExam.value=uxClone(remote);uxState.conflict=null;
  uxRestoreLocation(remote);const draft=uxReadDraft(id);
  if(draft?._invalidRaw){try{localStorage.setItem(`qm-invalid-draft:${id}`,draft._invalidRaw);uxRemoveDraft(id)}catch{}uxState.invalidDraft=true}
  else if(draft?.local&&Number(draft.base_revision)!==Number(remote.revision)){
   uxState.conflict={base:draft.base||null,local:uxClone(draft.local),remote};state.exam=uxClone(draft.local);state.exam.revision=remote.revision;state.dirty=true;uxState.version=Math.max(uxState.version,Number(draft.version)||1);state.stage=Math.max(0,Math.min(3,Number(draft.stage)||0));const localCard=state.exam.cards.findIndex(c=>c.id===draft.card_id);state.card=localCard<0?0:localCard;if(draft.material_id)uxState.materialByCard[state.exam.cards[state.card]?.id]=draft.material_id;uxState.tab=['question','answer','plan'].includes(draft.tab)?draft.tab:'question';if(state.stage>=2&&!state.exam.card_approval)state.stage=1;uxSetSaveStatus('conflict');
  }else if(draft?.local&&Number(draft.base_revision)===Number(remote.revision)){
   state.exam=draft.local;state.exam.revision=remote.revision;state.dirty=true;uxState.version=Math.max(uxState.version,Number(draft.version)||1);state.stage=Math.max(0,Math.min(3,Number(draft.stage)||0));const found=state.exam.cards.findIndex(c=>c.id===draft.card_id);state.card=found<0?Math.min(state.card,state.exam.cards.length-1):found;if(draft.material_id)uxState.materialByCard[state.exam.cards[state.card]?.id]=draft.material_id;uxState.tab=['question','answer','plan'].includes(draft.tab)?draft.tab:'question';uxSetSaveStatus('dirty');
  }
   if(state.stage>=2&&!state.exam.card_approval)state.stage=1;state.card=Math.max(0,Math.min(Number(state.card)||0,(state.exam.cards?.length||1)-1));if(state.authoringDraft?.examId!==id)state.authoringDraft=null;if(!state.authoringDraft)authoringRestoreLocal(id);if(state.authoringDraft?.mode)state.stage=0;renderSidebar();render();uxPersistLocation();
  if(state.exam.active_job)watch(state.exam.active_job);if(uxState.conflict)uxRenderConflict();else if(state.dirty)uxScheduleSave();
  if(uxState.invalidDraft){uxState.invalidDraft=false;uxShowInvalidDraft()}
 })}
openExam=uxOpenExam;
function requestSelect(c){const requested=authoringAiPending(c),label=c.authoring_mode==='manual'?'AI 재작성':String(c.question||'').trim()?'AI 재작성':'AI 요청';return '<label class="ai-check'+(requested?' is-checked':'')+'"><input type="checkbox" data-ai-request="'+esc(c.id)+'" value="'+(c.ai_requested?'yes':'no')+'" '+(requested?'checked':'')+'><span>'+label+'</span></label>'}
function standardField(c){
 const options=Object.entries(state.standards).filter(([,v])=>v.subject===state.exam.subject);
 return `<label class="full">성취기준 · ${esc(subjectLabel())}<select data-field="standard" aria-label="성취기준 선택"><option value="">성취기준 선택</option>${c.standard&&!options.some(([code])=>code===c.standard)?`<option selected value="${esc(c.standard)}">${esc(c.standard)} · 과목 확인 필요</option>`:''}${options.map(([code,v])=>`<option value="${esc(code)}" ${code===c.standard?'selected':''}>${esc(code)} · ${esc(v.name)}</option>`).join('')}</select></label>`
}
const uxBaseImagePlanFields=imagePlanFields;
imagePlanFields=function(c){
 const readonly=state.stage===2&&state.exam?.card_approval&&imageFlowState().step===0;
 if(readonly){
  const mode={strict:'정확 도형 · strict',mixed:'혼합 · mixed',flexible:'자유 표현 · flexible'}[c.image_mode]||'유형 미선택';
  const rules=[c.image_locked&&`SVG 규칙: ${c.image_locked}`,c.image_creative&&`창작 허용 영역: ${c.image_creative}`].filter(Boolean);
  const labels=[['물리량',c.image_text_physics],['수식',c.image_text_math],['한글',c.image_text_korean]].filter(([,value])=>String(value||'').trim());
  return `<section class="image-plan-readonly"><div><b>${esc(mode)}</b><button class="small-btn" data-ux-action="edit-image-plan">계획 수정</button></div><p>${esc(c.material||'장면 설명이 없습니다.')}</p>${rules.length?`<ul>${rules.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<p class="hint">유형별 그림 규칙이 비어 있습니다.</p>'}${c.image_text_none?'<p>그림에 넣을 글씨 없음</p>':labels.length?`<ul class="planned-labels">${labels.map(([kind,value])=>`<li>${kind}: ${esc(value)}</li>`).join('')}</ul>`:'<p class="hint">독립 글씨 계획을 확인해 주세요.</p>'}</section>`;
 }
 const html=uxBaseImagePlanFields(c);
 return html.replace('<option value="strict"','<option value="strict"').replace('>strict</option>','>정확 도형 · strict</option>').replace('>mixed</option>','>혼합 · mixed</option>').replace('>flexible</option>','>자유 표현 · flexible</option>')
  .replace('<button class="small-btn" data-layer-action="plan">','<label class="image-text-none"><input type="checkbox" data-bool="image_text_none" '+(c.image_text_none?'checked':'')+'> 그림에 넣을 글씨 없음</label><button class="small-btn" data-layer-action="plan">');
};
const uxBaseImageEditor=imageEditor;
imageEditor=function(){
 const card=state.exam?.cards?.[state.card],images=uxImageMaterials(card),active=uxActiveImageBlock(card);
 const selector=images.length>1?`<nav class="image-material-picker" aria-label="문항의 그림 자료">${images.map((block,index)=>`<button type="button" class="small-btn ${block.id===active?.id?'secondary':''}" data-image-material="${esc(block.id)}" aria-pressed="${block.id===active?.id}"><b>${esc(block.label||`그림 ${index+1}`)}</b><small>${esc(uxMaterialStatus(block))}</small></button>`).join('')}</nav>`:'';
 let html=uxBaseImageEditor();html=html.replace('<div class="image-flow-main">',`<div class="image-flow-main">${selector}`);
 const dock=`<div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div>`;
 if(html.endsWith('</section></div></div>'))return html.slice(0,-'</section></div></div>'.length)+`</section>${dock}</div></div>`;
 if(html.endsWith('</section></div>'))return html.slice(0,-'</section></div>'.length)+`</section>${dock}</div>`;
 return html;
};
function uxCliReady(){return !!state.boot?.cli?.[state.provider]}
async function uxGenerateQuestionIds(ids){
 await save();
 const wanted=[...new Set(ids)].filter(id=>state.exam.cards.some(card=>card.id===id&&authoringAiPending(card)));
 if(!wanted.length)throw Error('AI 작성 요청이 Yes인 문항이 없습니다.');
 const job=await api('/api/jobs',{exam_id:state.exam.id,action:'question',card_ids:wanted,feedback:$('#feedback')?.value||'',provider:state.provider,model:state.model});
 state.job=job;watch(job.id);
}
function uxPrimary(){
 const e=state.exam,c=current();if(!e)return `<div class="task-action"><span>시험을 선택하거나 새 시험을 만드세요.</span><button class="primary" id="newExamAction">새 시험 만들기</button></div>`;
 if(state.stage===0&&state.authoringDraft?.mode&&!state.authoringDraft.suspended){const isAi=state.authoringDraft.mode==='ai';return '<div class="task-action"><span>'+(state.authoringDraft.failed?'저장되지 않았습니다. 입력한 내용은 임시 초안으로 보관했습니다.':'초안은 저장해야 문항 목록에 반영됩니다.')+'</span><button type="button" class="secondary" data-authoring-cancel>목록으로 돌아가기</button><button type="submit" class="primary">'+(isAi?'생성 대기에 추가':'문항 저장')+'</button></div>'}
 if(uxState.conflict||uxState.status==='failed')return `<div class="task-action"><span>${uxState.conflict?'다른 저장본과 충돌했습니다. 내 초안과 최신 저장본을 비교해 선택하세요.':'변경 내용을 저장하지 못했습니다. 초안은 브라우저에 보존되어 있습니다.'}</span><button class="primary" data-ux-action="resolve-save">저장 문제 해결</button></div>`;
 if(state.job?.status==='running')return `<div class="task-action"><span>${esc(state.job.message||'작업 중')} · 취소하려면 진행 상태를 여세요.</span></div>`;
 if(state.stage===0){
  const targets=e.cards.filter(card=>authoringAiPending(card)),missing=targets.find(card=>!card.standard||!card.type||!card.difficulty||!card.idea);
  if(targets.length&&missing)return `<div class="task-action"><span>${missing.no}번 문항의 성취기준·유형·난이도·아이디어를 확인하세요.</span><button class="primary" data-ux-action="missing-design" data-card-id="${missing.id}">${missing.no}번 입력하기</button></div>`;
  const retryJob=state.job?.exam_id===e.id&&state.job.action==='question'&&state.job.status!=='running';
  const retryIds=retryJob?(state.job.item_ids||[]).filter(id=>e.cards.some(card=>card.id===id&&authoringAiPending(card))):[];
   if(retryIds.length)return `<div class="task-action"><span>${retryIds.length}개 문항이 실패했거나 아직 작성되지 않았습니다. 완료 문항은 다시 요청하지 않습니다.</span><button class="primary" data-ux-action="retry-questions" data-card-ids="${retryIds.join(',')}">AI 초안 ${retryIds.length}문항 다시 생성</button></div>`;
   if(!targets.length&&state.job?.exam_id===e.id&&state.job.action==='question'&&state.job.status==='completed')return `<div class="task-action"><span>${state.job.succeeded||state.job.total}개 문항을 작성했습니다. 교사 검토를 시작하세요.</span><button class="primary" data-ux-action="start-review">검토 시작</button></div>`;
  if(targets.length&&!uxCliReady())return `<div class="task-action"><span>${targets.length}문항을 AI로 작성하려면 먼저 연결하세요.</span><button class="primary" data-ux-action="connect">AI 연결</button></div>`;
   if(targets.length)return `<div class="task-action"><span>${targets.length}문항이 AI 작성 대상으로 선택되어 있습니다.</span><button class="primary" data-ux-action="generate-questions">AI 초안 ${targets.length}문항 생성</button></div>`;
  return `<div class="task-action"><span>AI 작성을 요청하거나 직접 문항을 추가하세요.</span><button class="primary" data-ux-action="add-card">문항 추가</button></div>`;
 }
 if(state.stage===1){
  if(!c.review_approved)return `<div class="task-action"><span>${c.no}번 문항을 확인한 뒤 개별 검토를 완료하세요.</span><button class="primary" data-ux-action="review-current">검토 완료</button></div>`;
  const next=e.cards.find(card=>!card.review_approved);
  if(next)return `<div class="task-action"><span>${e.cards.filter(card=>!card.review_approved).length}개 문항 검토가 남았습니다.</span><button class="primary" data-ux-action="next-review" data-card-id="${next.id}">${next.no}번 검토하기</button></div>`;
  const issues=e.card_validation?.issues||[],problem=issues.find(issue=>issue.code!=='review_required');
  if(problem)return `<div class="task-action"><span>${issues.length}개 출제안 확인 항목이 남았습니다.</span><button class="primary" data-ux-action="show-approval-summary">누락 ${issues.length}개 확인</button></div>`;
  if(!e.card_approval)return `<div class="task-action"><span>${e.cards.length}문항 · ${Number(e.cards.reduce((s,x)=>s+Number(x.points||0),0).toFixed(2))}점 · 미검토 0개</span><button class="primary" data-ux-action="approve-exam">출제안 승인</button></div>`;
  return `<div class="task-action"><span>출제안이 승인되었습니다. 그림이 있는 문항의 제작 계획을 확인하세요.</span><button class="primary" data-ux-action="go-images">그림 단계 열기</button></div>`;
 }
 if(state.stage===2){
  if(!e.card_approval)return `<div class="task-action"><span>그림 제작 전에 문항카드 전체 승인이 필요합니다.</span><button class="primary" data-ux-action="go-review">문항 검토로 이동</button></div>`;
  if(!e.cards.some(card=>uxImageMaterials(card).length))return `<div class="task-action"><span>그림이 필요한 문항이 없어 그림 단계를 마칠 수 있습니다.</span><button class="primary" data-ux-action="go-export">출력 준비</button></div>`;
 if(c.data_kind!=='image')return `<div class="task-action"><span>${c.no}번 문항은 그림 자료가 없습니다.</span><button class="primary" data-ux-action="next-image">다음 그림</button></div>`;
  const imageBlock=uxActiveImageBlock(e.cards[state.card]),imageLabel=imageBlock?.label||'그림';
  const flow=imageFlowState();if(flow.step===0)return `<div class="task-action"><span>${esc(imageLabel)} 계획은 저장됐습니다. 이 그림의 제작 범위를 확인한 뒤에 진행할 수 있습니다.</span><button class="primary" data-ux-action="confirm-plan">${esc(imageLabel)} 계획 확인</button></div>`;
  if(flow.step===1&&!uxCliReady())return `<div class="task-action"><span>그림 생성 전에 AI 연결을 완료하세요.</span><button class="primary" data-ux-action="connect">AI 연결</button></div>`;
  if(flow.step===1)return `<div class="task-action"><span>현재 문항의 배경 그림을 생성합니다. 글씨 레이어는 따로 보존합니다.</span><button class="primary" data-ux-action="generate-image">그림 생성</button></div>`;
  if(flow.step===2&&!c.labels_initialized&&uxCliReady())return `<div class="task-action"><span>배경 그림은 저장됐습니다. 글씨 레이어만 다시 배치합니다.</span><button class="primary" data-ux-action="retry-labels">글씨만 자동 배치</button></div>`;
  if(flow.step===2&&!c.labels_initialized)return `<div class="task-action"><span>AI 연결 후 글씨 레이어를 배치하거나 ‘글씨 없음’을 선택하세요.</span><button class="primary" data-ux-action="connect">AI 연결</button></div>`;
  if(flow.step===2)return `<div class="task-action"><span>캔버스에서 그림과 독립 글씨를 편집하고 저장하세요.</span><button class="primary" data-ux-action="save-image-edit">완성본 확인</button></div>`;
  if(!c.labels_initialized)return `<div class="task-action"><span>글씨 미리보기가 준비되기 전에는 그림을 확정할 수 없습니다.</span><button class="primary" data-ux-action="retry-labels">글씨만 자동 배치</button></div>`;
  if(c.image?.approved){const next=uxNextUnapprovedImage(state.card,imageBlock?.id);return `<div class="task-action"><span>${next?`${esc(imageLabel)} 그림이 확정되었습니다. ${esc(next.block.label||'다음 그림')}을 확인하세요.`:'모든 그림이 확정되었습니다.'}</span><button class="primary" data-ux-action="${next?'next-image':'go-export'}">${next?'다음 그림':'출력 준비'}</button></div>`}
  return `<div class="task-action"><span>합성 미리보기를 확인한 뒤 ${esc(imageLabel)} 그림을 시험지에 넣도록 확정하세요.</span><button class="primary" data-ux-action="approve-image">${esc(imageLabel)} 그림 최종 확정</button></div>`;
 }
 const ready=e.validation?.ready,latest=e.exports?.[e.exports.length-1],fresh=latest&&latest.content_digest===e.content_digest;
 if(latest&&fresh)return `<div class="task-action"><span>현재 출제 내용의 시험지와 해설이 준비됐습니다.</span><a class="primary action-link" href="/download/${e.id}/${latest.id}/출제결과.zip" download>전체 받기</a></div>`;
 if(!ready){const issues=e.validation?.issues||[],first=issues[0],target=first?.material_id?uxIssueMaterialLabel(first):'';const detail=first?.code==='image_plan_unconfirmed'?`저장된 ${target||'그림'} 계획을 아직 확인하지 않았습니다.`:first?.code==='image_plan_invalid'?`${target||'그림'} 제작 계획의 내용을 보완해 주세요.`:first?.code==='image_approval_required'?`${target||'그림'}의 진행 단계에서 최종 확인을 마쳐 주세요.`:`${issues.length||1}개 항목을 해결하면 파일을 만들 수 있습니다.`;const actionText=first?uxIssueActionLabel(first):`${issues.length||1}개 문제 해결`;return `<div class="task-action"><span>${detail}</span><button class="primary" data-ux-action="first-output-issue">${actionText}</button></div>`}
 return `<div class="task-action"><span>${e.cards.length}문항 · 100점 · 승인된 문항과 그림이 확인됐습니다.</span><button class="primary" data-ux-action="create-export">시험지 만들기</button></div>`;
}
function uxNextUnapprovedImage(cardIndex,materialId){
 const cards=state.exam?.cards||[],currentCard=cards[cardIndex],currentList=uxImageMaterials(currentCard),start=currentList.findIndex(block=>block.id===materialId);
 for(let offset=0;offset<cards.length;offset++){
  const index=(cardIndex+offset)%cards.length,images=uxImageMaterials(cards[index]);
  for(let j=0;j<images.length;j++){
   if(offset===0&&j<=start)continue;
   if(!images[j].image_plan_approval||!images[j].image?.approved)return {cardIndex:index,card:cards[index],block:images[j]};
  }
 }
 return null;
}
function uxActionBar(){return uxPrimary()}
function uxOnePrimary(){
 const root=$('#workspace');if(!root)return;
 const candidates=[...root.querySelectorAll('.primary')];
 const action=root.querySelector('#taskActionBar .task-action .primary');
 for(const button of candidates)button.classList.toggle('primary',button===action);
}
function uxRefreshPrimary(){const dock=$('#taskActionBar');if(!dock)return;dock.innerHTML=uxPrimary();uxOnePrimary()}
function approvalBar(){
 const e=state.exam;if(!e)return '';
 if(state.stage===1&&e.card_approval)return `<div class="approval-status" role="status"><b>출제안 승인 완료</b><span>문항을 수정하면 재승인이 필요합니다.</span><button class="small-btn" data-ux-action="go-images">그림 단계</button></div>`;
 if(state.stage===2&&!e.card_approval)return `<div class="approval-status approval-needed" role="status"><b>출제안 승인이 필요합니다.</b><span>승인 전 그림 생성·가져오기·출력은 서버에서도 차단됩니다.</span><button class="small-btn" data-ux-action="go-review">문항 검토로 이동</button></div>`;
 return '';
}
function rail(imageOnly=false){
 if(imageOnly)uxSyncBulkImages();
 const items=state.exam.cards.map((c,i)=>{const images=uxImageMaterials(c),done=images.filter(block=>block.image_plan_approval&&block.image?.approved).length,button=`<button class="item-btn ${i===state.card?'active':''}" data-select="${i}" data-reorder="${esc(c.id)}" draggable="true" aria-current="${i===state.card?'true':'false'}"><span class="circle">${String(i+1).padStart(2,'0')}</span><span class="rail-label">${imageOnly?(images.length?`${images.length}개 그림`:'그림 없음'):(c.type||'문항')}</span>${imageOnly&&images.length?`<small>${done}/${images.length}개 확정</small>`:`<small>${esc(c.idea||'아이디어 미입력')}</small>`}</button>`;return imageOnly?`<div class="image-rail-item">${button}${images.length?`<label class="bulk-image-check"><input type="checkbox" data-bulk-image="${esc(c.id)}" ${uxState.bulkImageIds.has(c.id)?'checked':''}><span>${c.no}번 포함 · ${images.length}개</span></label>`:''}</div>`:button}).join('');
 const bulk=imageOnly?`<details class="image-bulk-tools"><summary>여러 그림 작업 <span id="uxBulkImageCount">0개 선택</span></summary><p>목록에서 생성할 그림을 선택한 뒤 선택 범위만 실행합니다. 승인되고 계획을 확인한 문항만 처리됩니다.</p><div class="buttons-wrap"><button type="button" class="small-btn" id="uxBulkSelectAll">그림 문항 모두 선택</button><button type="button" class="small-btn" id="uxBulkClearSelection">선택 해제</button><button type="button" class="small-btn" data-ux-action="generate-images" id="uxBulkGenerate" disabled>선택한 그림 생성</button></div></details>`:'';
 return `<nav class="item-rail" aria-label="문항 목록">${items}<button id="addCard" class="small-btn">＋ 문항 추가</button>${bulk}</nav>`;
}
function uxSyncBulkImages(){if(uxState.bulkExamId!==state.exam?.id){uxState.bulkExamId=state.exam?.id||null;uxState.bulkImageIds.clear()}const ids=new Set((state.exam?.cards||[]).filter(c=>uxImageMaterials(c).length).map(c=>c.id));for(const id of uxState.bulkImageIds)if(!ids.has(id))uxState.bulkImageIds.delete(id)}
function uxUpdateBulkImageBar(){uxSyncBulkImages();const count=uxState.bulkImageIds.size,node=$('#uxBulkImageCount'),button=$('#uxBulkGenerate');if(node)node.textContent=`${count}개 선택`;if(button)button.disabled=!count||state.job?.status==='running';document.querySelectorAll('[data-bulk-image]').forEach(input=>{input.checked=uxState.bulkImageIds.has(input.dataset.bulkImage)})}
function overview(){
 const e=state.exam,cs=e.cards;
 return `<section class="design-stage"><div class="stage-toolbar"><div><h2>출제 범위와 문항 의도를 정하세요</h2><p>문항마다 AI 초안 또는 직접 작성 방식을 선택합니다. 생성 대기 문항만 AI가 처리합니다.</p></div><div class="buttons-wrap"><button id="addCard" class="secondary">문항 추가</button><button id="openScorePanel" class="secondary">배점</button></div></div><section class="panel design-table-panel"><div class="panel-head"><div><h3>${cs.length}개 문항 카드</h3><small>문항 번호는 입력한 카드 수에 따라 이어집니다.</small></div><details class="design-more"><summary aria-label="문항 더보기">더보기</summary><div><button data-ux-action="connect">AI 연결 설정</button><button class="danger" id="deleteExam">작업실 삭제</button></div></details></div><div class="table-scroll"><table class="card-table"><thead><tr><th>번호</th><th>아이디어</th><th>성취기준</th><th>유형</th><th>난이도</th><th>배점</th><th>정답 번호</th><th>AI 작성</th><th>상태</th><th>작업</th></tr></thead><tbody>${cs.map((c,i)=>{const points=String(c.points??'').trim(),idea=String(c.idea||'아이디어 입력'),answer=uxAnswerNumber(c.answer),answerClass='①②③④⑤'.includes(answer)?' design-answer-number':'';return `<tr data-card="${i}" data-reorder="${esc(c.id)}" draggable="true"><td class="design-number-cell">${designReorderHandle(c,i)}<button class="row-open" data-card="${i}" aria-label="${i+1}번 문항 열기">${String(i+1).padStart(2,'0')}</button></td><td><div class="design-idea-cell row-idea-cell"><button class="row-open row-idea" data-card="${i}" aria-label="${i+1}번 문항 아이디어: ${esc(idea)}"><span class="design-idea-text">${esc(idea)}</span></button>${designImageThumbs(c)}</div></td><td><button class="row-open" data-card="${i}" title="${esc(c.standard_name||'성취기준 선택')}">${esc(c.standard||'선택')}</button></td><td>${esc(c.type||'미선택')}</td><td>${esc(c.difficulty||'미선택')}</td><td><output class="design-readonly-value" aria-label="${i+1}번 배점">${points?`${esc(points)}점`:'미입력'}</output></td><td><output class="design-readonly-value${answerClass}" aria-label="${i+1}번 정답 번호">${esc(answer)}</output></td><td>${requestSelect(c)}</td><td>${badge(c)}</td><td><div class="row-actions" aria-label="${i+1}번 문항 작업"><button type="button" class="row-action" data-duplicate-card-id="${esc(c.id)}" aria-label="${i+1}번 문항 복제" title="${i+1}번 문항 복제" ${uxState.duplicateInFlight.has(c.id)||state.job?.status==='running'||cs.length>=100?'disabled':''}><svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg></button><button type="button" class="row-action row-delete-action" data-remove-card-id="${esc(c.id)}" aria-label="${i+1}번 문항 삭제" title="${i+1}번 문항 삭제" ${state.job?.status==='running'?'disabled':''}><svg aria-hidden="true" viewBox="0 0 24 24" focusable="false"><path d="M3 6h18M8 6V4h8v2m-11 0 1 14h12l1-14M10 10v6M14 10v6"></path></svg></button></div></td></tr>`}).join('')}</tbody></table></div><p id="reorderAnnounce" class="sr-only" aria-live="polite" aria-atomic="true"></p><div class="table-foot"><span>시험 합계 <b>${Number(cs.reduce((n,c)=>n+Number(c.points||0),0).toFixed(2))}점</b> · 배점과 합답형 비율은 승인 전에 검사합니다.</span><span>순서 변경: 끌기 또는 ⠿에 초점을 두고 Space → ↑/↓ → Space · ↑ 많음/↓ 적음은 참고입니다.</span></div></section></section><div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div>`;
}
function uxPlanSummary(c){return `<div class="image-plan-summary"><b>${esc(c.image_mode||'유형 미선택')}</b><span>${esc(c.material||'그림 장면 설명을 입력해 주세요.')}</span><button type="button" class="small-btn" data-review-tab="plan">계획 편집</button></div>`}
function editor(){
 const c=current(),tab=c.data_kind==='image'?uxState.tab:(uxState.tab==='answer'?'answer':'question');
 const dataKindOptions=[['none','자료 없음'],['image','그림'],['text','글상자'],['table','표']];
 const questionFields=`<div class="fields review-fields">${field('stem','문두',{full:true,textarea:true,placeholder:'문항에서 제시하는 상황을 적어 주세요.'})}<label class="full">자료 종류<select data-field="data_kind">${dataKindOptions.map(([v,l])=>`<option value="${v}" ${c.data_kind===v?'selected':''}>${l}</option>`).join('')}</select></label>${c.data_kind==='image'?`<label class="full">그림 장면 설명<textarea data-field="material" placeholder="그림에 필요한 배경과 요소를 설명해 주세요.">${esc(c.material||'')}</textarea></label>${uxPlanSummary(c)}`:c.data_kind==='text'||c.data_kind==='table'?field('material',c.data_kind==='table'?'자료 표 · 마크다운':'자료 글상자',{full:true,textarea:true,tall:true}):''}${field('question','발문',{full:true,textarea:true,placeholder:'학생이 답해야 하는 내용을 적어 주세요.'})}${c.type==='합답형'?field('statements','보기 · ㄱ, ㄴ, ㄷ',{full:true,textarea:true}):c.statements?`<details class="preserved-field full"><summary>기존 보기가 있습니다 · 보기 편집</summary>${field('statements','보기 · ㄱ, ㄴ, ㄷ',{full:true,textarea:true})}</details>`:''}</div>`;
 const answerFields=`<div class="fields review-fields">${field('choices','선택지 · ①~⑤',{full:true,textarea:true,tall:true})}${field('answer','정답 번호 · 1~5',{placeholder:'예: 2'})}${field('concepts','내용 영역',{placeholder:'예: 운동량'})}${field('explanation','정답·해설',{full:true,textarea:true,tall:true})}</div><label class="check-row"><input type="checkbox" data-bool="calculation" ${c.calculation?'checked':''}>계산이 포함된 문항</label>${c.calculation?`<label class="full">계산식 <span class="muted">이름 | 왼쪽 식 | 오른쪽 식</span><textarea id="checksInput" placeholder="속력 | 2*3 | 6">${esc((c.checks||[]).map(x=>`${x.label} | ${x.lhs} | ${x.rhs}`).join('\n'))}</textarea></label><div class="buttons-wrap"><button id="verify" class="secondary">계산 확인</button></div><div id="checkResults"></div><details class="help-inline"><summary>계산 확인의 범위</summary><p>입력한 등식이 서로 같은지 검사합니다. 물리 상황과 정답 대응은 직접 확인해 주세요.</p></details>`:''}`;
 const planFields=c.data_kind==='image'?imagePlanFields(c):`<div class="empty-plan"><b>이 문항은 그림 자료를 사용하지 않습니다.</b><p>그림 계획 입력은 그림 자료를 선택하면 나타납니다. 기존 그림 관련 입력이 있으면 저장된 채로 유지됩니다.</p></div>`;
 return `<div class="edit-layout ux-edit-layout">${rail()}<section class="panel review-panel"><div class="panel-head"><div><h2>${c.no}번 문항</h2><p>${esc(c.idea||'핵심 아이디어를 아직 입력하지 않았습니다.')}</p></div>${badge(c)}</div><div class="panel-body"><details class="criteria-panel"><summary>출제 기준 <span>${esc(c.standard||'성취기준 선택')} · ${esc(c.type||'유형 선택')} · ${esc(c.difficulty||'난이도 선택')}</span></summary><div class="fields">${standardField(c)}${field('type','문항 유형',{select:['',...state.boot.types]})}${field('difficulty','난이도',{select:['','하','중','상']})}${field('points','배점',{placeholder:'4.2'})}${field('idea','문항 핵심 아이디어',{full:true,textarea:true})}</div><p id="standardName" class="hint">${esc(c.standard_name||'')}</p><label class="ai-feedback-field">수정 요청 <span class="muted">선택 사항</span><textarea data-field="ai_feedback" placeholder="예: 물리 상황은 유지하고 비교 조건을 한 가지 더 제시해 주세요.">${esc(c.ai_feedback||'')}</textarea></label></details><nav class="review-tabs" aria-label="문항 편집 구역"><button data-review-tab="question" aria-selected="${tab==='question'}">문항</button><button data-review-tab="answer" aria-selected="${tab==='answer'}">정답·해설</button>${c.data_kind==='image'?`<button data-review-tab="plan" aria-selected="${tab==='plan'}">그림 계획</button>`:''}</nav><div class="review-tab-panel" data-review-panel="question" ${tab==='question'?'':'hidden'}>${questionFields}</div><div class="review-tab-panel" data-review-panel="answer" ${tab==='answer'?'':'hidden'}>${answerFields}</div>${c.data_kind==='image'?`<div class="review-tab-panel" data-review-panel="plan" ${tab==='plan'?'':'hidden'}>${planFields}</div>`:''}<div class="review-notes">${c.review_note?`<details><summary>생성·검토 메모</summary><p>${esc(c.review_note)}</p></details>`:''}</div><div class="review-secondary-actions"><button class="small-btn" id="saveBtn">저장</button><button class="small-btn danger" id="removeCard">문항 삭제</button></div><div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div></div></section><aside class="panel preview"><div class="preview-head"><span>문항 미리보기</span><span>${String(c.no).padStart(2,'0')}</span></div><div id="previewSheet">${preview(c)}</div><div class="preview-footer">최종 수식과 쪽 배치는 한글 출력에서 확인합니다.</div></aside></div>`;
}
function uxImageStepForMaterial(block){return !block?.image_plan_approval?0:block.image?.approved?3:block.image?block.labels_initialized?3:2:1}
function uxMaterialStatus(block){
 if(block.kind!=='image')return block.kind==='table'?'표 자료':'글상자';
 if(block.image?.approved)return '그림 최종 확정';
 if(!block.image_plan_approval)return '그림 계획 확인 필요';
 if(!block.image)return '그림 생성 대기';
 return block.labels_initialized?'최종 확인 필요':'글씨 배치 필요';
}
function uxImageDefaults(){return {image_mode:'',image_locked:'',image_creative:'',image_text_physics:'',image_text_math:'',image_text_korean:'',image_text_none:false,image_plan_version:2,image_plan_approval:null,image_labels:[],labels_initialized:false,image_scene:null,image:null}}
function uxImageLabel(index){return `(${['가','나','다','라','마','바','사','아','자','차','카','타','파','하'][Math.min(index,13)]||`그림 ${index+1}`})`}
function uxAddMaterial(card,kind){
 const blocks=uxEnsureMaterials(card),imageCount=blocks.filter(block=>block.kind==='image').length;
 const block={id:uxMakeId(),kind,label:kind==='image'?uxImageLabel(imageCount):kind==='table'?'표':'글상자',content:'',...(kind==='image'?uxImageDefaults():{})};
 blocks.push(block);uxSyncMaterialAliases(card);uxState.materialByCard[card.id]=block.id;return block;
}
function uxTouchMaterialEdit(card,{imageContext=null}={}){
 card.review_approved=false;state.exam.card_approval=null;
 if(imageContext){imageContext.image_plan_approval=null;if(imageContext.image)imageContext.image.approved=false}
 markDirty(false);
}
function uxMaterialOptions(kind){return [['image','그림'],['text','글상자'],['table','표']].map(([value,label])=>`<option value="${value}" ${kind===value?'selected':''}>${label}</option>`).join('')}
function uxLegacyMaterialEditor(card){
 const kind=card.data_kind||'none',hasImage=kind==='image';
 return `<section class="material-manager full"><div class="material-manager-head"><div><h3>자료</h3><p>문항 초안에는 성취기준·유형·난이도·아이디어만 필요합니다. 자료와 배점은 뒤에서 다듬어도 됩니다.</p></div></div><label class="full">자료 종류<select data-field="data_kind">${[['none','자료 없음'],['image','그림'],['text','글상자'],['table','표']].map(([value,label])=>`<option value="${value}" ${kind===value?'selected':''}>${label}</option>`).join('')}</select></label>${hasImage?`<label class="full">그림 장면 설명<textarea data-field="material" placeholder="그림의 장면과 꼭 들어갈 요소를 적어 주세요.">${esc(card.material||'')}</textarea></label>${uxPlanSummary(card)}`:kind==='text'||kind==='table'?field('material',kind==='table'?'표 내용 · 마크다운':'글상자 내용',{full:true,textarea:true,tall:true}):'<p class="hint">그림, 글상자, 표를 필요에 따라 여러 개 추가할 수 있습니다.</p>'}<div class="material-add-actions"><button type="button" class="small-btn" data-material-convert>자료 이름·표지·순서 편집</button><button type="button" class="small-btn" data-material-add="image">＋ 그림 추가</button><button type="button" class="small-btn" data-material-add="text">＋ 글상자 추가</button><button type="button" class="small-btn" data-material-add="table">＋ 표 추가</button></div></section>`;
}
function uxCanonicalMaterialsEditor(card){
 const blocks=Array.isArray(card.materials)?card.materials:[];
 const blockHtml=blocks.map((block,index)=>`<article class="material-block" data-material-block="${esc(block.id)}"><header class="material-block-head"><b>${index+1}. ${esc(block.label||({image:'그림',text:'글상자',table:'표'}[block.kind]||'자료'))}</b><div class="material-block-controls"><button type="button" class="small-btn" data-material-move="-1" data-material-id="${esc(block.id)}" aria-label="${index+1}번 자료 위로" ${index===0?'disabled':''}>↑</button><button type="button" class="small-btn" data-material-move="1" data-material-id="${esc(block.id)}" aria-label="${index+1}번 자료 아래로" ${index===blocks.length-1?'disabled':''}>↓</button><button type="button" class="small-btn danger" data-material-remove="${esc(block.id)}">삭제</button></div></header><div class="fields material-block-fields"><label>자료 이름 / 표지<input data-material-property="label" data-material-id="${esc(block.id)}" value="${esc(block.label||'')}" placeholder="예: (가), 실험 결과, 자료 표"></label><label>자료 종류<select data-material-property="kind" data-material-id="${esc(block.id)}">${uxMaterialOptions(block.kind)}</select></label><label class="full">${block.kind==='image'?'그림 장면 및 제작 설명':block.kind==='table'?'표 내용 · 마크다운':'글상자 내용'}<textarea class="${block.kind==='image'?'':'tall'}" data-material-property="content" data-material-id="${esc(block.id)}" placeholder="${block.kind==='image'?'그림의 배경과 요소를 설명해 주세요.':block.kind==='table'?'| 항목 | 값 |\n|---|---|\n| A | 1 |':'자료 본문을 입력해 주세요.'}">${esc(block.content||'')}</textarea></label>${block.kind==='image'?`<div class="full material-image-status"><span>${esc(uxMaterialStatus(block))}</span><button type="button" class="small-btn" data-plan-material="${esc(block.id)}">이 그림 계획 열기</button></div>`:''}</div></article>`).join('');
 return `<section class="material-manager full"><div class="material-manager-head"><div><h3>자료 · ${blocks.length}개</h3><p>목록 순서가 시험지 순서입니다. 그림·글상자·표를 여러 개 함께 둘 수 있습니다.</p></div></div><div class="material-add-actions"><button type="button" class="small-btn" data-material-add="image">＋ 그림 추가</button><button type="button" class="small-btn" data-material-add="text">＋ 글상자 추가</button><button type="button" class="small-btn" data-material-add="table">＋ 표 추가</button></div><div class="material-block-list">${blockHtml||'<div class="empty-materials">아직 자료가 없습니다. 필요한 자료를 추가하세요.</div>'}</div></section>`;
}
function uxMaterialPlanPicker(card){
 const images=uxImageMaterials(card);if(images.length<2)return '';
 const active=uxActiveImageBlock(card);
 return `<nav class="material-plan-picker" aria-label="그림별 제작 계획">${images.map((block,index)=>`<button type="button" class="small-btn ${block.id===active?.id?'secondary':''}" data-plan-material="${esc(block.id)}" aria-pressed="${block.id===active?.id}">${esc(block.label||`그림 ${index+1}`)} · ${esc(uxMaterialStatus(block))}</button>`).join('')}</nav>`;
}
editor=function(){
 const c=current(),hasImage=uxImageMaterials(state.exam.cards[state.card]).length>0;
 const tab=hasImage?uxState.tab:(uxState.tab==='answer'?'answer':'question');
 const questionFields=`<div class="fields review-fields">${field('stem','문두',{full:true,textarea:true,placeholder:'문항에서 제시하는 상황을 적어 주세요.'})}${Array.isArray(c.materials)?uxCanonicalMaterialsEditor(state.exam.cards[state.card]):uxLegacyMaterialEditor(state.exam.cards[state.card])}${field('question','발문',{full:true,textarea:true,placeholder:'학생이 답해야 하는 내용을 적어 주세요.'})}${c.type==='합답형'?field('statements','보기 · ㄱ, ㄴ, ㄷ',{full:true,textarea:true}):c.statements?`<details class="preserved-field full"><summary>기존 보기가 있습니다 · 보기 편집</summary>${field('statements','보기 · ㄱ, ㄴ, ㄷ',{full:true,textarea:true})}</details>`:''}</div>`;
 const answerFields=`<div class="fields review-fields">${field('choices','선택지 · ①~⑤',{full:true,textarea:true,tall:true})}${field('answer','정답 번호 · 1~5',{placeholder:'예: 2'})}${field('concepts','내용 영역',{placeholder:'예: 운동량'})}${field('explanation','정답·해설',{full:true,textarea:true,tall:true})}</div><label class="check-row"><input type="checkbox" data-bool="calculation" ${c.calculation?'checked':''}>계산이 포함된 문항</label>${c.calculation?`<label class="full">계산식 <span class="muted">이름 | 왼쪽 식 | 오른쪽 식</span><textarea id="checksInput" placeholder="속력 | 2*3 | 6">${esc((c.checks||[]).map(x=>`${x.label} | ${x.lhs} | ${x.rhs}`).join('\n'))}</textarea></label><div class="buttons-wrap"><button id="verify" class="secondary">계산 확인</button></div><div id="checkResults"></div><details class="help-inline"><summary>계산 확인의 범위</summary><p>입력한 등식이 서로 같은지 검사합니다. 물리 상황과 정답 대응은 직접 확인해 주세요.</p></details>`:''}`;
 const planFields=hasImage?`${uxMaterialPlanPicker(state.exam.cards[state.card])}${imagePlanFields(c)}`:`<div class="empty-plan"><b>이 문항은 그림 자료를 사용하지 않습니다.</b><p>그림 계획은 그림 자료를 추가하면 나타납니다. 기존 단일 자료는 그대로 유지됩니다.</p></div>`;
  return `<div class="edit-layout ux-edit-layout">${rail()}<section class="panel review-panel"><div class="panel-head"><div><h2>${c.no}번 문항</h2><p>${esc(c.idea||'핵심 아이디어를 아직 입력하지 않았습니다.')}</p></div>${badge(c)}</div><div class="panel-body"><details class="criteria-panel"><summary>출제 기준 <span>${esc(c.standard||'성취기준 선택')} · ${esc(c.type||'유형 선택')} · ${esc(c.difficulty||'난이도 선택')}</span></summary><div class="fields">${standardField(c)}${field('type','문항 유형',{select:['',...state.boot.types]})}${field('difficulty','난이도',{select:['','하','중','상']})}${field('idea','문항 핵심 아이디어',{full:true,textarea:true})}</div><p id="standardName" class="hint">${esc(c.standard_name||'')}</p><label class="ai-feedback-field">수정 요청 <span class="muted">선택 사항</span><textarea data-field="ai_feedback" placeholder="예: 물리 상황은 유지하고 비교 조건을 한 가지 더 제시해 주세요.">${esc(c.ai_feedback||'')}</textarea></label><button type="button" class="secondary" data-ux-action="rewrite-current">AI로 수정</button></details><nav class="review-tabs" aria-label="문항 편집 구역"><button data-review-tab="question" aria-selected="${tab==='question'}">문항</button><button data-review-tab="answer" aria-selected="${tab==='answer'}">정답·해설</button>${hasImage?`<button data-review-tab="plan" aria-selected="${tab==='plan'}">그림 계획</button>`:''}</nav><div class="review-tab-panel" data-review-panel="question" ${tab==='question'?'':'hidden'}>${questionFields}</div><div class="review-tab-panel" data-review-panel="answer" ${tab==='answer'?'':'hidden'}>${answerFields}</div>${hasImage?`<div class="review-tab-panel" data-review-panel="plan" ${tab==='plan'?'':'hidden'}>${planFields}</div>`:''}<div class="review-notes">${c.review_note?`<details><summary>생성·검토 메모</summary><p>${esc(c.review_note)}</p></details>`:''}</div><div class="review-secondary-actions"><button class="small-btn" id="openScorePanel">배점 조정</button><button class="small-btn" id="saveBtn">저장</button><button class="small-btn danger" id="removeCard">문항 삭제</button></div><div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div></div></section><aside class="panel preview"><div class="preview-head"><span>문항 미리보기</span><span>${String(c.no).padStart(2,'0')}</span></div><div id="previewSheet">${preview(c)}</div><div class="preview-footer">최종 수식과 쪽 배치는 한글에서 확인합니다.</div></aside></div>`;
};
function uxIssueMaterialLabel(issue){
 if(!issue?.material_id||!issue?.card_id)return '';
 const card=state.exam?.cards?.find(item=>item.id===issue.card_id),block=uxVisibleMaterials(card).find(item=>item.id===issue.material_id);
 return block?.label||'';
}
function uxIssueActionLabel(issue){
 if(issue.code==='image_plan_invalid')return '계획 내용 수정 →';
 if(issue.code==='image_plan_unconfirmed')return '그림 계획 확인 →';
 if(issue.code==='image_approval_required')return '그림 진행 이어가기 →';
 if(issue.field==='points'||issue.stage==='score')return '배점 조정 →';
 return '해결 위치 열기 →';
}
function uxMarkdownTable(source){
 const rows=String(source||'').split(/\r?\n/).map(line=>line.trim()).filter(line=>line.startsWith('|')&&line.endsWith('|')).map(line=>line.slice(1,-1).split('|').map(cell=>cell.trim()));
 if(rows.length<2)return `<div class="material-box material-table-text">${uxPreviewText(source||'')}</div>`;
 const cells=rows.filter(row=>!row.every(cell=>/^:?-{3,}:?$/.test(cell))).map(row=>`<tr>${row.map(cell=>`<td>${uxPreviewText(cell)}</td>`).join('')}</tr>`).join('');
 return `<div class="material-table-wrap"><table class="material-preview-table">${cells}</table></div>`;
}
function uxPreviewText(value){return previewMathText(value)}
function uxRenderPreviewMath(){renderPreviewMath()}
function uxAnswerNumber(answer){const value=String(answer??'').trim(),circled='①②③④⑤';if(/^[1-5]$/.test(value))return circled[Number(value)-1];return value.length===1&&circled.includes(value)?value:value||'미입력'}
preview=function(c){
 const blocks=uxVisibleMaterials(c),materialHtml=blocks.map((block,index)=>{
  const title=block.label?`<b class="material-preview-label">${esc(block.label)}</b>`:'';
  if(block.kind==='image'){
   const im=block.image,filename=im?.approved&&im.final_file?im.final_file:block.image_scene&&im?.edited_file?im.edited_file:im?.file;
   return `<section class="material-preview-item material-preview-image" data-preview-material="${esc(block.id)}">${title}${filename?`<img src="/assets/${state.exam.id}/${esc(filename)}" alt="${c.no}번 ${esc(block.label||`자료 그림 ${index+1}`)}">`:`<div class="material-box muted">${title||'그림 자료'} · 그림 생성 대기</div>`}</section>`;
  }
  return `<section class="material-preview-item material-preview-${block.kind}" data-preview-material="${esc(block.id)}">${title}${block.kind==='table'?uxMarkdownTable(block.content):`<div class="material-box material-prose">${uxPreviewText(block.content||'')}</div>`}</section>`;
 }).join('');
 const stem=String(c.stem||'').trim(),question=String(c.question||'').trim();
 return `<div class="sheet"><div class="sheet-title">${esc(state.exam.title)}</div><p class="preview-stem"><b>${c.no}.</b> ${stem?uxPreviewText(c.stem):'<span class="preview-empty-field">문두가 비어 있습니다.</span>'}</p>${materialHtml}<p class="preview-question">${question?uxPreviewText(c.question):'<span class="preview-empty-field">발문이 비어 있습니다.</span>'} ${c.points?`[${esc(c.points)}점]`:''}</p>${c.statements?`<div class="material-box">${uxPreviewText(c.statements)}</div>`:''}<div class="choice">${uxPreviewText(c.choices)}</div></div>`;
};
function exportsView(){
 const e=state.exam,v=e.validation||{errors:[],issues:[],warnings:[],ready:false},latest=e.exports?.[e.exports.length-1],fresh=latest&&latest.content_digest===e.content_digest;
 const issueRows=(v.issues||[]).map(item=>{const card=state.exam.cards.find(c=>c.id===item.card_id),material=uxIssueMaterialLabel(item),cardLabel=card?`${card.no}번${material?` · ${material}`:''}`:'';return `<li><button class="issue-link" data-issue-code="${esc(item.code)}" data-issue-card="${esc(item.card_id||'')}" data-issue-material="${esc(item.material_id||'')}" data-issue-field="${esc(item.field||'')}" data-issue-stage="${esc(item.stage||'review')}"><b>${esc(cardLabel||item.message)}</b><span>${esc(item.message)}</span><em>${uxIssueActionLabel(item)}</em></button></li>`}).join('');
 const outputs=e.exports||[],mainFiles=['시험지_학생용.hml','시험지_교사용.hml','정답과해설.md'];
 const first=latest?mainFiles.filter(x=>latest.files.includes(x)):[],other=latest?latest.files.filter(x=>!first.includes(x)&&x!=='출제결과.zip'):[];
 const hwpButton=bundle=>state.boot?.hwp_conversion_available?`<button class="small-btn" data-recalc="${esc(bundle.id)}">HWP 변환</button>`:'';
 return `<div class="export-layout ux-export-layout"><section class="panel"><div class="panel-head"><div><h2>받을 파일을 준비합니다</h2><p>${e.cards.length}문항 · ${Number(e.cards.reduce((s,c)=>s+Number(c.points||0),0).toFixed(2))}점</p></div><span class="badge ${v.ready?'success':'warn'}">${v.ready?'출력 검사 통과':`${(v.issues||[]).length}개 확인 필요`}</span></div><div class="panel-body">${v.issues?.length?`<div class="issue-panel"><h3>해결할 항목</h3><ul class="issues">${issueRows}</ul></div>`:'<div class="notice">문항·배점·승인과 그림 확인을 통과했습니다.</div>'}${v.warnings?.map(x=>`<div class="notice warn">${esc(x)}</div>`).join('')||''}${latest?`<section class="latest-export"><div><h3>최근 출력 · 문항 내용 ${fresh?'최신':'수정 전'}</h3><p>${fresh?'현재 출제 내용으로 만든 파일입니다.':'현재 내용과 다른 출력본입니다. 다시 만들어 최신 상태를 반영하세요.'}</p></div><div class="priority-files">${first.map(name=>uxDownload(e.id,latest.id,name)).join('')}${latest.files.includes('출제결과.zip')?uxDownload(e.id,latest.id,'출제결과.zip','전체 받기'):''}${hwpButton(latest)}</div><details class="other-files"><summary>기타 파일 ${other.length}개</summary>${other.map(name=>uxDownload(e.id,latest.id,name)).join('')}</details>${!fresh?'<p class="outdated-notice" role="status">현재 내용과 다른 출력본 · 이전 파일은 그대로 보존됩니다.</p>':''}</section>`:'<div class="placeholder">출력 전 점검이 끝나면 학생용·교사용 시험지와 정답·해설을 만들 수 있습니다.</div>'}<p class="print-note">한글에서 인쇄 배치와 수식 크기를 확인해 주세요. 파일 생성은 실제 인쇄 확인을 뜻하지 않습니다.</p><div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div></div></section><aside class="panel export-history"><div class="panel-head"><h3>이전 버전 <span class="muted">${Math.max(0,outputs.length-(latest?1:0))}</span></h3></div><div class="panel-body">${outputs.length>1?outputs.slice(0,-1).reverse().map(bundle=>`<details class="export-version"><summary>${esc(bundle.created.replace('T',' '))} · ${bundle.content_digest===e.content_digest?'현재 내용':'문항 내용 '+bundle.revision+' 버전'}</summary>${bundle.files.filter(n=>['시험지_학생용.hml','시험지_교사용.hml','정답과해설.md','출제결과.zip','시험지_학생용.hwp'].includes(n)).map(name=>uxDownload(e.id,bundle.id,name,name==='출제결과.zip'?'전체 받기':undefined)).join('')}${hwpButton(bundle)}</details>`).join(''):'<p class="hint">새 출력본을 만들면 이전 버전이 이곳에 보존됩니다.</p>'}</div></aside></div>`;
}
function uxDownload(eid,bid,name,label){const href=`/download/${eid}/${bid}/${encodeURIComponent(name)}`,extension=name.split('.').pop().toUpperCase();return `<a class="download ux-download" href="${href}" download><span>${esc(label||name)}</span><small>${extension}</small></a>`}
function render(){
 const e=state.exam,job=state.job&&e&&state.job.exam_id===e.id&&state.job.status==='completed'?state.job:null;
 const jobLabel=job?.action==='question'?`${job.succeeded??job.progress}문항 작성됨`:job?`그림 작업 ${job.succeeded??job.progress}개 완료`:'';
 const jobChip=job?`<div id="uxJobChip" data-status="completed" role="status" title="${esc(job.message)}"><span>${esc(jobLabel)}</span><button type="button" data-ux-job-log>작업 기록</button><button type="button" data-ux-job-dismiss aria-label="완료 상태 닫기">×</button></div>`:'';
 $('#examTitle').textContent=e?.title||'내 시험';$('#crumbTitle').textContent=e?.title||'내 시험';$('#subtitle').textContent='';$('#topActions').innerHTML=e?`<span class="saved" id="saveState" data-status="${uxState.status}">저장됨</span>${jobChip}<button id="saveBtn" class="quiet save-inline">저장</button><details class="exam-menu"><summary aria-label="시험 메뉴">⋯</summary><div><button data-ux-action="home">내 시험 목록</button><button data-ux-action="new-exam">새 시험 만들기</button><button data-ux-action="connect">AI 연결 설정</button><button class="danger" id="deleteExam">작업실 삭제</button></div></details>`:'';
 const steps=['설계','검토','그림','출력'];$('#steps').innerHTML=steps.map((x,i)=>`<button class="step ${state.stage===i?'active':''}" data-stage="${i}" ${e?'':'disabled'} aria-current="${state.stage===i?'step':'false'}"><span class="step-name">${x}</span></button>`).join('');
 $('#approvalBar').innerHTML=e?approvalBar():'';const isDistribution=e&&state.stage<2;$('#liveStats').hidden=!isDistribution;$('#secondaryStats').hidden=!e||isDistribution;
 if(!e)$('#workspace').innerHTML=welcome();else $('#workspace').innerHTML=state.stage===0&&state.authoringDraft?.mode&&!state.authoringDraft.suspended?authoringDraftView():[overview,editor,imageEditor,exportsView][state.stage]();
 bindWorkspace();if(state.authoringDraft?.suspended&&state.stage===0)$('#workspace').insertAdjacentHTML('afterbegin','<section class="authoring-suspended notice" role="status"><div><b>임시 문항 초안이 보관되어 있습니다.</b><p>저장 전 입력 내용은 문항 수에 포함되지 않습니다.</p></div><button type="button" data-authoring-resume>이어 쓰기</button><button type="button" data-authoring-discard>임시 초안 삭제</button></section>');renderStats();renderPreviewMath();bindReorder();if(typeof initLayers==='function')initLayers();if(typeof initImageFlow==='function')initImageFlow();if(state.job?.status==='running')setBusy(true);
 uxSetSaveStatus(uxState.status);uxBindDelete();uxPersistLocation();uxOnePrimary();uxUpdateBulkImageBar();
 document.body.dataset.studioStage=e?String(state.stage):'welcome';$('#steps').hidden=!e;$('#workspaceHome').classList.toggle('active',!e);$('#workspaceHome').disabled=state.job?.status==='running';
}
function welcome(){
 const exams=state.boot?.exams||[];return `<section class="exam-dashboard"><div class="dashboard-heading"><div><h2>내 시험</h2><p>진행 중인 시험을 열어 마지막 작업부터 이어가세요.</p></div><button class="secondary" data-ux-action="new-exam">새 시험 만들기</button></div>${exams.length?`<div class="exam-project-grid">${exams.map(e=>{const subject=state.boot.subjects.find(s=>s.id===e.subject)?.name||e.subject||'과목 미지정',imageProgress=Number(e.image_total)>0?`그림 ${Number(e.image_total)-Number(e.image_remaining||0)}/${e.image_total}개 확정`:'';return `<button class="exam-project" data-open-exam="${esc(e.id)}"><span class="project-title">${esc(e.title)}</span><span class="project-meta">${esc(subject)} · ${e.card_count||0}문항${imageProgress?` · ${imageProgress}`:''}</span><span class="project-meta">${esc(e.next_action||`${e.review_remaining||0}개 검토 남음`)}</span><span class="project-meta">${esc((e.updated||'').slice(0,10).replaceAll('-','.'))} 수정</span><span class="project-open">이어서 작성 →</span></button>`}).join('')}</div>`:'<div class="empty-projects"><h3>아직 만든 시험이 없습니다.</h3><p>시험 제목과 과목을 정하고 첫 문항을 추가하세요.</p></div>'}</section><div class="review-action-dock" id="taskActionBar">${uxPrimary()}</div>`;
}
function renderSidebar(){
 const subjectSelect=$('#createForm').elements.subject,previousSubject=subjectSelect.value;
 subjectSelect.innerHTML='<option value="">과목을 선택해 주세요</option>'+state.boot.subjects.map(x=>`<option value="${esc(x.id)}" title="${esc(x.id)} · ${x.count}개 성취기준">${esc(x.name)}</option>`).join('');subjectSelect.value=previousSubject;
 $('#examList').innerHTML='';const src=$('#createForm').elements.source;src.innerHTML='<option value="blank">빈 문항카드로 시작</option><option value="upload">엑셀에서 가져오기</option>'+state.boot.legacy.map((e,i)=>`<option value="legacy:${i}">기존 회차 복사 · ${esc(e.split('/')[1])}</option>`).join('');
}
function renderStats(){
 const el=$('#liveStats'),secondary=$('#secondaryStatsBody'),inSecondary=!!state.exam&&state.stage>=2,target=inSecondary?secondary:el;
 if(!el||!target)return;el.hidden=!state.exam||inSecondary;$('#secondaryStats').hidden=!inSecondary;
 const examId=state.exam?.id||null;
 if(uxStatsUi.examId!==examId){uxStatsUi.examId=examId;uxStatsUi.standardsExpanded=false;uxStatsUi.helpExpanded=false}
 if(!state.exam){el.innerHTML='';if(secondary)secondary.innerHTML='';uxStatsObserveSize();return}
 const cards=state.exam.cards||[],count=(key,v)=>cards.filter(c=>c[key]===v).length,answer=c=>{const a=String(c.answer||'').trim();return a&&'①②③④⑤'.includes(a)?'①②③④⑤'.indexOf(a)+1:Number(a)};
 const typeLabels={'단일 정답형':'단일','합답형':'합답','불완전 문장형':'불완전','짝짓기형':'짝짓기'};
 const visibleLabel=(label,value)=>label==='문항 유형'?(typeLabels[value]||value):label==='정답'?'①②③④⑤'[Number(value)-1]:value;
 const group=(label,values,counts,missing)=>{
  const total=counts.reduce((a,b)=>a+b,0);
  const rows=values.map((value,i)=>{
   const level=distributionNudge(counts[i],total,values.length),pct=total?Math.round(counts[i]/total*100):0;
   const hint=level==='high'?'↑ 평균보다 많은 편':level==='low'?'↓ 평균보다 적은 편':'비중 참고';
   const name=label==='문항 유형'?value:visibleLabel(label,value);
   const title=`${label} ${name}: ${counts[i]}개 (${pct}%). ${hint}. 균등 비중은 참고용이며 출제 의도에 따라 조정할 수 있습니다.`;
   return `<span class="count-chip nudge-${level}${counts[i]===0?' is-zero':''}" role="img" tabindex="0" data-distribution="${esc(label)}" data-value="${esc(value)}" data-tooltip="${esc(label==='문항 유형'?`${value} · ${counts[i]}개`:title)}" title="${esc(title)}" aria-label="${esc(title)}">${esc(visibleLabel(label,value))} <b class="count-value${counts[i]===0?' is-zero':''}">${counts[i]}</b>${level==='high'?'<span class="nudge-mark" aria-hidden="true">↑</span>':level==='low'?'<span class="nudge-mark" aria-hidden="true">↓</span>':''}</span>`;
  }).join('');
  return `<div class="count-group"><strong>${esc(label)}</strong><div class="distribution-chips">${rows}${missing?`<span class="count-chip count-missing">미입력 <b class="count-value">${missing}</b></span>`:''}</div></div>`;
 };
 const used={};for(const c of cards)if(c.standard)used[c.standard]=(used[c.standard]||0)+1;
 const standards=Object.entries(used),standardCode=([code,n])=>{
  const name=state.standards[code]?.name||code,title=`${code} · ${name} · ${n}문항`;
  return `<span class="standard-code" data-standard-code="${esc(code)}" tabindex="0" role="group" title="${esc(title)}" aria-label="${esc(title)}" data-tooltip="${esc(title)}">${esc(code)} <b>${n}</b><span class="standard-code-name" aria-hidden="true">${esc(name)}</span></span>`;
 };
 const standardPreview=standards.length?`${standards.map(([code,n])=>`<span class="standard-preview-code">${esc(code)} <b>${n}</b></span>`).join('')}<span class="standard-more-count" hidden></span>`:'<span class="muted">선택한 기준 없음</span>';
 const total=Number(cards.reduce((s,c)=>s+(Number(c.points)||0),0).toFixed(2));
 target.innerHTML=`<div class="stats-inner"><div class="counts-top"><b>총 ${cards.length}문항</b><span>AI 요청 ${cards.filter(c=>c.ai_requested).length}개 · ${total}점</span><details class="distribution-help" ${uxStatsUi.helpExpanded?'open':''}><summary data-stats-help-toggle aria-expanded="${uxStatsUi.helpExpanded}" aria-label="분포 안내" title="분포 안내">ⓘ</summary><div class="distribution-help-panel" role="note">각 분포의 입력 합계가 항목 수×2개 이상부터 표시합니다. ↑는 같은 분포에서 평균보다 많은 항목, ↓는 평균보다 적은 항목입니다. 균등 비중은 참고 기준이며, 난이도도 고정 비율에 맞출 필요는 없습니다.</div></details></div><div class="counts-grid">${group('문항 유형',state.boot.types,state.boot.types.map(t=>count('type',t)),count('type',''))}${group('난이도',['상','중','하'],['상','중','하'].map(t=>count('difficulty',t)),count('difficulty',''))}${group('정답',[1,2,3,4,5],[1,2,3,4,5].map(n=>cards.filter(c=>answer(c)===n).length),cards.filter(c=>!answer(c)).length)}</div><div class="standard-counts"><strong>성취기준 ${standards.length}개</strong><div class="standard-preview">${standardPreview}</div>${standards.length?`<details class="standard-disclosure" ${uxStatsUi.standardsExpanded?'open':''}><summary data-stats-standards-toggle aria-expanded="${uxStatsUi.standardsExpanded}" aria-label="사용 성취기준 더 보기">더 보기</summary><div class="standard-count-list" role="group" aria-label="사용 성취기준 목록">${standards.map(standardCode).join('')}</div></details>`:''}</div></div>`;
 const renderedExamId=examId;
 target.querySelector('.distribution-help')?.addEventListener('toggle',event=>{const details=event.currentTarget;if(!details.isConnected||uxStatsUi.examId!==renderedExamId||state.exam?.id!==renderedExamId)return;uxStatsUi.helpExpanded=details.open;details.querySelector('summary')?.setAttribute('aria-expanded',String(details.open));uxStatsMeasureHeight()});
 target.querySelector('.standard-disclosure')?.addEventListener('toggle',event=>{const details=event.currentTarget;if(!details.isConnected||uxStatsUi.examId!==renderedExamId||state.exam?.id!==renderedExamId)return;uxStatsUi.standardsExpanded=details.open;details.querySelector('summary')?.setAttribute('aria-expanded',String(details.open));uxStatsMeasureHeight()});
 uxStatsObserveSize();
}
function uxOpenScorePanel(focusCardId=null){
 return action(async()=>{await save();const result=await api('/api/score-preview',{exam_id:state.exam.id});
  const total=Number(state.exam.cards.reduce((sum,card)=>sum+Number(card.points||0),0).toFixed(2));
  $('#scoreDialog').innerHTML=`<div class="dialog-top"><div><div class="eyebrow">배점 패널</div><h2>문항 검토 뒤 배점을 정하세요</h2></div><button class="icon-btn" data-close="scoreDialog" aria-label="닫기">×</button></div><p class="hint">배점은 초안 작성과 AI 문항 생성에 필요하지 않습니다. 각 문항을 검토한 뒤 직접 입력하거나 권장 배점을 적용하세요.</p><div class="score-groups">${['상','중','하'].map(level=>{const rows=result.points.filter(x=>x.difficulty===level);return `<section><h3>${level} · ${rows.length}문항</h3><p>권장 ${rows.length?rows.map(x=>x.after).join(' · '):'없음'}</p></section>`}).join('')}</div><table class="score-preview"><thead><tr><th>문항</th><th>난이도</th><th>직접 입력</th><th>권장</th></tr></thead><tbody>${result.points.map(x=>`<tr class="${String(x.before)!==String(x.after)?'changed':''}" data-score-card="${esc(x.card_id)}" tabindex="-1"><td>${x.no}번</td><td>${esc(x.difficulty||'미정')}</td><td><label class="score-input-label"><input type="number" min="0" step="0.1" data-score-points="${esc(x.card_id)}" value="${esc(x.before||'')}" placeholder="나중에 입력"><span>점</span></label></td><td>${esc(x.after)}점</td></tr>`).join('')}</tbody></table><p class="notice">현재 합계 <b id="scoreCurrentTotal">${total}</b>점 · 전체 승인과 출력 전 합계가 100점이어야 합니다. 점수를 바꾸면 문항 검토와 전체 승인을 다시 해야 합니다.</p><div class="dialog-actions"><button data-close="scoreDialog">닫기</button><button id="saveManualScore" class="secondary">직접 배점 저장</button><button id="applyScore" class="primary">권장 배점 적용</button></div>`;
  $('#scoreDialog').showModal();if(focusCardId){const row=$(`[data-score-card="${CSS.escape(focusCardId)}"]`);row?.scrollIntoView({block:'center'});row?.querySelector('[data-score-points]')?.focus({preventScroll:true})}else $('#saveManualScore').focus({preventScroll:true});
  $('#applyScore').onclick=()=>action(async()=>{state.exam=await api('/api/allocate',{exam_id:state.exam.id});state.exam=await api('/api/exams/'+state.exam.id);state.dirty=false;uxBaseExam.value=uxClone(state.exam);uxRemoveDraft(state.exam.id);$('#scoreDialog').close();render();toast('권장 배점을 적용했습니다. 변경된 문항을 다시 검토하세요.')});
   const scoreDialog=$('#scoreDialog');scoreDialog.insertAdjacentHTML('beforeend','<p id="scoreError" class="score-error" role="alert" hidden></p>');scoreDialog.querySelectorAll('[data-score-points]').forEach(input=>{input.max='100';input.removeAttribute('aria-invalid')});
   const validateScoreInputs=()=>{const edits=[],invalid=[];for(const input of scoreDialog.querySelectorAll('[data-score-points]')){const card=state.exam.cards.find(item=>item.id===input.dataset.scorePoints),raw=input.value.trim();if(!card){invalid.push({input,message:'문항을 찾을 수 없습니다. 최신 저장본을 다시 열어 주세요.'});continue}if(!raw){edits.push({card,next:''});input.removeAttribute('aria-invalid');continue}const value=Number(raw);if(!Number.isFinite(value)||value<=0||value>100){invalid.push({input,message:'배점은 비워 두거나 0 초과 100 이하로 입력해 주세요.'});input.setAttribute('aria-invalid','true');continue}input.removeAttribute('aria-invalid');edits.push({card,next:String(value)})}if(invalid.length){const message=invalid[0].message,error=scoreDialog.querySelector('#scoreError');error.textContent=invalid.length===1?message:`${message} (${invalid.length}개 값 확인 필요)`;error.hidden=false;invalid[0].input.focus();return null}scoreDialog.querySelector('#scoreError').hidden=true;return edits};
   scoreDialog.oninput=event=>{if(!event.target.matches('[data-score-points]'))return;const sum=[...scoreDialog.querySelectorAll('[data-score-points]')].reduce((n,input)=>n+(Number(input.value)||0),0);$('#scoreCurrentTotal').textContent=Number(sum.toFixed(2));scoreDialog.querySelector('#scoreError').hidden=true};
   $('#saveManualScore').onclick=()=>action(async()=>{const edits=validateScoreInputs();if(!edits)return;const changed=edits.filter(({card,next})=>String(card.points||'')!==next);for(const {card,next} of changed){card.points=next;card.review_approved=false}if(changed.length){state.exam.card_approval=null;markDirty(false);await save();state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam)}$('#scoreDialog').close();render();toast(`직접 배점을 저장했습니다. 현재 합계는 ${Number(state.exam.cards.reduce((n,c)=>n+Number(c.points||0),0).toFixed(2))}점입니다.`)});
  });
 }
async function uxApproveWithDiscrepancy(card,kind,materialId=null){
 return await approveWithDiscrepancy(card,kind,materialId);
}
 function uxReviewSummary(){
 const e=state.exam,issues=e.card_validation?.issues||[],remaining=e.cards.filter(c=>!c.review_approved).length,points=Number(e.cards.reduce((s,c)=>s+Number(c.points||0),0).toFixed(2)),planMissing=e.cards.flatMap(uxImageMaterials).filter(block=>!block.image_plan_approval).length;
 $('#reviewSummaryDialog').innerHTML=`<div class="dialog-top"><div><div class="eyebrow">출제안 검토</div><h2>승인 전에 전체 범위를 확인하세요</h2></div><button class="icon-btn" data-close="reviewSummaryDialog" aria-label="닫기">×</button></div><div class="approval-summary"><p><b>${e.cards.length}문항</b><span>총 ${points}점 · 미검토 ${remaining}개 · 그림 계획 누락 ${planMissing}개</span></p></div>${issues.length?`<ul class="issues">${issues.map(i=>{const card=e.cards.find(c=>c.id===i.card_id),material=uxIssueMaterialLabel(i);return `<li><button class="issue-link" data-issue-code="${esc(i.code)}" data-issue-card="${esc(i.card_id||'')}" data-issue-material="${esc(i.material_id||'')}" data-issue-field="${esc(i.field||'')}" data-issue-stage="${esc(i.stage||'review')}"><b>${esc(card?`${card.no}번${material?` · ${material}`:''}`:i.message)}</b><span>${esc(i.message)}</span><em>${uxIssueActionLabel(i)}</em></button></li>`}).join('')}</ul>`:'<div class="notice">문항 내용, 배점, 검토 상태를 확인했습니다. 승인하면 실제 그림 제작이 열립니다.</div>'}<div class="dialog-actions"><button data-close="reviewSummaryDialog">계속 검토</button><button id="confirmExamApproval" class="primary" ${issues.length?'disabled':''}>출제안 승인</button></div>`;
 $('#reviewSummaryDialog').showModal();$('#confirmExamApproval').onclick=()=>action(async()=>{await save();await api('/api/approve-cards',{exam_id:state.exam.id});state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);state.dirty=false;state.stage=2;$('#reviewSummaryDialog').close();render();toast('출제안 승인이 저장되었습니다. 이제 실제 그림 제작을 시작할 수 있습니다.')});
}
function uxSetCurrentById(id){uxStoreImageToolState();const index=state.exam.cards.findIndex(c=>c.id===id);if(index>=0)state.card=index;else state.card=Math.min(state.card,state.exam.cards.length-1)}
function uxFocusMissingDesign(card){
 const key=['standard','type','difficulty','idea'].find(name=>!String(card?.[name]||'').trim());if(!key)return;
 $('.criteria-panel')?.setAttribute('open','');
 requestAnimationFrame(()=>{const field=$(`[data-field="${key}"]`);if(field){field.scrollIntoView({block:'center'});field.focus({preventScroll:true})}});
}
async function uxDeleteCardById(id){
 try{await save()}catch(error){return {removed:false,persisted:false,error}}
 if(state.exam.cards.length<=1)throw Error('최소 한 문항은 남겨 주세요.');
 if(state.job?.status==='running')throw Error('생성이 끝난 뒤 문항을 삭제해 주세요.');
 uxStoreImageToolState();
 const activeId=current()?.id,removedIndex=state.exam.cards.findIndex(card=>card.id===id);if(removedIndex<0)return {removed:false,persisted:false,error:new Error('삭제할 문항을 찾을 수 없습니다.')};
 state.exam.cards=state.exam.cards.filter(card=>card.id!==id).map((card,index)=>({...card,no:index+1}));
 state.card=activeId===id?Math.min(removedIndex,state.exam.cards.length-1):state.exam.cards.findIndex(card=>card.id===activeId);
 state.exam.card_approval=null;markDirty(false);
 try{await save()}catch(error){render();return {removed:true,persisted:false,error,removedIndex,remaining:state.exam.cards.length}}
 render();return {removed:true,persisted:true,removedIndex,remaining:state.exam.cards.length};
}
function uxSyncDesignRowActions(){
 const locked=state.job?.status==='running'||uxState.duplicateInFlight.size>0,atLimit=(state.exam?.cards.length||0)>=100;
 document.querySelectorAll('[data-duplicate-card-id]').forEach(button=>{button.disabled=locked||atLimit;button.setAttribute('aria-busy',String(uxState.duplicateInFlight.has(button.dataset.duplicateCardId)))});
 document.querySelectorAll('[data-remove-card-id]').forEach(button=>{button.disabled=locked});
}
function uxAnnounceDesignAction(message,cardId=null,action='duplicate'){
 requestAnimationFrame(()=>{
  const announce=$('#reorderAnnounce');if(announce)announce.textContent=message;
  if(!cardId||state.stage!==0)return;
  const button=$(`[data-${action}-card-id="${CSS.escape(cardId)}"]`);if(button){button.scrollIntoView({block:'nearest',inline:'nearest'});button.focus({preventScroll:true})}
 });
}
function uxDuplicateRequestKey(examId,cardId){return `qm-duplicate-request:${examId}:${cardId}`}
function uxGetDuplicateRequestId(examId,cardId){
 const cacheKey=`${examId}:${cardId}`;let requestId=uxState.duplicateRequestIds.get(cacheKey);if(requestId)return requestId;
 try{requestId=sessionStorage.getItem(uxDuplicateRequestKey(examId,cardId))||''}catch{}
 if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId))requestId=crypto.randomUUID();
 uxState.duplicateRequestIds.set(cacheKey,requestId);try{sessionStorage.setItem(uxDuplicateRequestKey(examId,cardId),requestId)}catch{}
 return requestId;
}
function uxClearDuplicateRequestId(examId,cardId){uxState.duplicateRequestIds.delete(`${examId}:${cardId}`);try{sessionStorage.removeItem(uxDuplicateRequestKey(examId,cardId))}catch{}}
async function uxDuplicateCardById(id){
 if(uxState.duplicateInFlight.size)return;
 if(!state.exam)throw Error('현재 작업실을 찾을 수 없습니다.');
 if(state.job?.status==='running')throw Error('생성이 끝난 뒤 문항을 복제해 주세요.');
 if(state.exam.cards.length>=100)throw Error('문항은 최대 100개까지 만들 수 있습니다.');
 if(!state.exam.cards.some(card=>card.id===id))throw Error('복제할 문항을 찾을 수 없습니다.');
 const examId=state.exam.id,requestId=uxGetDuplicateRequestId(examId,id);let completed=false;
 uxState.duplicateInFlight.add(id);uxSyncDesignRowActions();
 try{
  await save();
  if(state.exam?.id!==examId)throw Error('작업실이 바뀌어 복제를 시작하지 않았습니다.');
  if(uxState.conflict)throw Error('저장 충돌을 해결한 뒤 문항을 복제해 주세요.');
  if(state.job?.status==='running')throw Error('생성이 끝난 뒤 문항을 복제해 주세요.');
  if(state.exam.cards.length>=100)throw Error('문항은 최대 100개까지 만들 수 있습니다.');
  if(!state.exam.cards.some(card=>card.id===id))throw Error('복제할 문항을 찾을 수 없습니다.');
  const base=uxClone(state.exam),version=uxState.version;
  const result=await api('/api/duplicate-card',{exam_id:examId,revision:state.exam.revision,card_id:id,request_id:requestId});
  const server=result?.exam,newId=result?.card_id;
  if(!server||server.id!==examId||!newId||!server.cards?.some(card=>card.id===newId))throw Error('복제 응답에서 새 문항을 확인하지 못했습니다. 같은 요청으로 다시 시도해 주세요.');
  completed=true;uxClearDuplicateRequestId(examId,id);
  if(state.exam?.id!==examId){toast('문항 복제는 완료됐습니다. 해당 작업실에서 결과를 확인해 주세요.');return}
  let nextExam=server;
  if(uxState.version!==version||state.dirty){
   const local=uxClone(state.exam),merged=uxThreeWayMerge(base,local,server);
   if(merged.conflicts.length){uxState.conflict={base,local,remote:uxClone(server)};uxSetSaveStatus('conflict');uxWriteDraft();uxRenderConflict();toast('문항 복제는 완료됐습니다. 동시에 수정된 내용의 저장 충돌을 해결해 주세요.');return}
   nextExam=merged.merged;
  }
  const needsSave=!uxJsonEqual(nextExam,server);
  state.exam=nextExam;state.exam.revision=server.revision;state.stage=0;uxBaseExam.value=uxClone(server);
  if(needsSave){state.dirty=true;uxState.version++;uxWriteDraft();try{await save()}catch(error){if(error?.code!=='revision_conflict')uxShowSaveError(error)}}
  else{state.dirty=false;uxRemoveDraft(examId);uxSetSaveStatus('saved')}
  render();const clone=state.exam.cards.find(card=>card.id===newId),number=clone?.no||state.exam.cards.findIndex(card=>card.id===newId)+1;
  uxAnnounceDesignAction(`${number}번 문항을 복제했습니다.`,newId,'duplicate');
  toast(state.dirty?`${number}번 문항을 복제했습니다. 수정 사항은 저장 상태를 확인해 주세요.`:`${number}번 문항을 복제했습니다.`);
 }finally{uxState.duplicateInFlight.delete(id);uxSyncDesignRowActions()}
}
function uxEnsureCardDeleteDialog(){
 let dialog=$('#uxDeleteCardDialog');if(dialog)return dialog;
 dialog=document.createElement('dialog');dialog.id='uxDeleteCardDialog';dialog.setAttribute('aria-labelledby','uxDeleteCardTitle');dialog.innerHTML='<div class="dialog-top"><div><div class="eyebrow">문항 삭제</div><h2 id="uxDeleteCardTitle"></h2></div><button type="button" class="icon-btn" data-cancel-card-delete aria-label="닫기">×</button></div><p id="uxDeleteCardIdea" class="delete-card-idea"></p><p id="uxDeleteCardNote" class="hint"></p><div class="dialog-actions"><button type="button" data-cancel-card-delete>취소</button><button type="button" class="danger" data-confirm-card-delete>문항 삭제</button></div>';
 document.body.append(dialog);
 dialog.addEventListener('cancel',event=>{event.preventDefault();if(dialog.dataset.busy==='true')return;dialog.close('cancel')});
 dialog.addEventListener('close',()=>{const returnFocus=uxState.deleteReturnFocus;uxState.deleteReturnFocus=null;if(returnFocus?.isConnected)requestAnimationFrame(()=>returnFocus.focus({preventScroll:true}))});
 dialog.addEventListener('click',event=>{
  const cancel=event.target.closest('[data-cancel-card-delete]');if(cancel){event.preventDefault();dialog.close('cancel');return}
  const confirm=event.target.closest('[data-confirm-card-delete]');if(!confirm)return;
  event.preventDefault();const id=dialog.dataset.cardId,card=state.exam?.cards.find(item=>item.id===id);if(!card)return;
  if(state.exam.cards.length<=1){confirm.disabled=true;return}
  if(state.job?.status==='running'){toast('생성이 끝난 뒤 문항을 삭제해 주세요.');return}
  uxSetCardDeleteDialogBusy(dialog,true);
  action(async()=>{
   try{
    const removedNo=card.no,index=state.exam.cards.findIndex(item=>item.id===id),focusId=state.exam.cards[index+1]?.id||state.exam.cards[index-1]?.id||null;
    const result=await uxDeleteCardById(id);
    if(!result?.persisted){dialog.close('save-failed');if(result?.removed){state.stage=0;uxAnnounceDesignAction(`${removedNo}번 문항 삭제를 저장하지 못했습니다. 입력 내용은 보존했습니다.`,focusId,'duplicate')}uxShowSaveError(result?.error||new Error('문항 삭제를 저장하지 못했습니다.'));return}
    dialog.close('deleted');state.stage=0;
    uxAnnounceDesignAction(`${removedNo}번 문항을 삭제했습니다.`,focusId,'duplicate');toast(`${removedNo}번 문항을 삭제했습니다.`);
   }catch(error){dialog.close('failed');if(error?.code==='revision_conflict'||state.dirty)uxShowSaveError(error);else toast(error?.message||'문항을 삭제하지 못했습니다.')}finally{uxSetCardDeleteDialogBusy(dialog,false)}
  });
 });
 return dialog;
}
function uxSetCardDeleteDialogBusy(dialog,busy){
 dialog.dataset.busy=String(busy);dialog.setAttribute('aria-busy',String(busy));
 dialog.querySelectorAll('[data-cancel-card-delete]').forEach(button=>{button.disabled=busy});
 const confirm=dialog.querySelector('[data-confirm-card-delete]');if(confirm)confirm.disabled=busy||!state.exam||state.exam.cards.length<=1;
}
function uxOpenCardDeleteDialog(id,button){
 const card=state.exam?.cards.find(item=>item.id===id);if(!card)return;
 if(state.job?.status==='running'){toast('생성이 끝난 뒤 문항을 삭제해 주세요.');return}
 const dialog=uxEnsureCardDeleteDialog(),lastCard=state.exam.cards.length<=1;
 uxState.deleteReturnFocus=button;dialog.dataset.cardId=id;
 $('#uxDeleteCardTitle').textContent=`${card.no}번 문항을 삭제할까요?`;
 $('#uxDeleteCardIdea').innerHTML=`<b>문항 아이디어</b><br>${esc(card.idea||'아이디어 미입력')}`;
 $('#uxDeleteCardNote').textContent=lastCard?'최소 한 문항은 남겨야 하므로 이 문항은 삭제할 수 없습니다.':'삭제하면 목록과 시험 문항에서 제거됩니다.';
 dialog.querySelector('[data-confirm-card-delete]').disabled=lastCard;dialog.showModal();dialog.querySelector('[data-cancel-card-delete]:not(.icon-btn)').focus({preventScroll:true});
}
function uxSetTab(tab){uxState.tab=tab;uxPersistLocation();render();document.querySelector(`[data-review-tab="${tab}"]`)?.focus({preventScroll:true})}
function uxIssueTarget(button){
 const code=button.dataset.issueCode,issueStage=button.dataset.issueStage,fieldName=button.dataset.issueField;
 const stage=code==='image_plan_unconfirmed'||code==='image_approval_required'?2:code==='image_plan_invalid'?1:({design:0,review:1,'image-plan':1,image:2,score:1,approval:1}[issueStage]??1);
 return action(async()=>{
  await save();button.closest('dialog')?.close();if(button.dataset.issueCard)uxSetCurrentById(button.dataset.issueCard);
  const card=state.exam.cards[state.card],materialId=button.dataset.issueMaterial;
  if(materialId)uxSelectMaterial(card,materialId,{preferImage:true});
  state.stage=stage;
  if(stage===1){uxState.tab=code==='image_plan_invalid'||issueStage==='image-plan'||fieldName?.startsWith('image_')?'plan':['answer','explanation','choices','checks'].includes(fieldName)?'answer':'question'}
  if(stage===1&&uxImageMaterials(card).length===0&&uxState.tab==='plan')uxState.tab='question';
  if(stage===2){
   const block=uxActiveImageBlock(card),flow=imageFlowState();
   if(code==='image_plan_unconfirmed'||!block?.image_plan_approval)flow.step=0;
   else if(code==='image_approval_required')flow.step=block.image?(block.labels_initialized?3:2):1;
  }
  render();
  if(fieldName==='points'){await uxOpenScorePanel(button.dataset.issueCard||null);return}
  requestAnimationFrame(()=>{
   if(fieldName==='standard'||fieldName==='type'||fieldName==='difficulty'||fieldName==='idea')$('.criteria-panel')?.setAttribute('open','');
   const target=fieldName==='checks'?'#checksInput':fieldName?`[data-field="${CSS.escape(fieldName)}"]`:null;
   const input=target?$(target):null;
   if(stage===2&&code==='image_plan_unconfirmed'){const confirm=$('#confirmImagePlan');if(confirm){confirm.scrollIntoView({block:'center'});confirm.focus({preventScroll:true});return}}
   if(input){input.scrollIntoView({block:'center'});input.focus({preventScroll:true})}else $('#imageFlowHeading')?.focus({preventScroll:true});
  });
 });
}
function uxBindDelete(){
 const bind=()=>{const button=$('#deleteExam');if(button)button.onclick=()=>{if(state.job?.status==='running')throw Error('진행 중인 작업을 먼저 완료하거나 취소해 주세요.');$('#deleteTitle').textContent=state.exam.title;$('#deleteDialog').showModal()};};bind();
}
function uxNewExam(){
 $('#createDialog').showModal();requestAnimationFrame(()=>$('#createForm').elements.title.focus());
}
document.addEventListener('submit',event=>{
 if(event.target.id!=='createForm')return;event.preventDefault();event.stopImmediatePropagation();action(async()=>{
  const form=event.target,title=form.elements.title.value.trim(),subject=form.elements.subject.value,source=form.elements.source.value;
  if(!title){form.elements.title.setCustomValidity('시험 제목을 입력해 주세요.');form.elements.title.reportValidity();form.elements.title.setCustomValidity('');return}
  if(!subject){form.elements.subject.focus();form.elements.subject.setCustomValidity('과목을 선택해 주세요.');form.elements.subject.reportValidity();form.elements.subject.setCustomValidity('');return}
  const data={title,subject};if(source==='upload'){const file=form.elements.xlsx.files[0];if(!file){form.elements.xlsx.focus();throw Error('엑셀 파일을 선택해 주세요.')}data.xlsx=await file64(file)}if(source.startsWith('legacy:'))data.legacy=state.boot.legacy[Number(source.split(':')[1])];
   const created=await api('/api/create',data);state.exam=created;state.authoringDraft=null;state.authoringChoiceBackup=null;state.card=0;state.stage=0;state.dirty=false;uxBaseExam.value=uxClone(created);uxState.version=0;uxState.tab='question';uxState.conflict=null;state.boot=await api('/api/bootstrap');$('#createDialog').close();form.reset();$('#uploadLabel').hidden=true;renderSidebar();render();
 });
},true);
document.addEventListener('input',event=>{
 const authoringForm=event.target.closest('#authoringDraftForm'),session=state.authoringDraft;if(authoringForm&&session?.mode){const draft=session.draft,material=event.target.closest('[data-material-property]');if(material){event.stopImmediatePropagation();const block=uxEnsureMaterials(draft).find(item=>item.id===material.dataset.materialId);if(!block)return;const property=material.dataset.materialProperty,value=material.value;if(property==='kind'){if(!['image','text','table'].includes(value))return;block.kind=value;if(value==='image')for(const [key,defaultValue] of Object.entries(uxImageDefaults()))if(!(key in block))block[key]=uxClone(defaultValue)}else if(property==='label')block.label=value;else if(property==='content')block.content=value;uxSyncMaterialAliases(draft);authoringPersistLocal();if(property==='kind')requestAnimationFrame(()=>{render();document.querySelector('[data-material-property="kind"][data-material-id="'+block.id+'"]')?.focus({preventScroll:true})});return}const field=event.target.closest('[data-authoring-field]');if(field){event.stopImmediatePropagation();const key=field.dataset.authoringField;draft[key]=field.value;if(key==='standard'){const found=state.standards[field.value];draft.standard_name=found?.name||'';draft.standard_note=found?.note||'';const note=authoringForm.querySelector('[data-authoring-standard-note]');if(note)note.textContent=found?.name||'성취기준을 선택해 주세요.'}if(key==='materials_request'){const count=authoringForm.querySelector('#materialsRequestCount');if(count)count.textContent=Array.from(field.value).length+'/4000자'}authoringPersistLocal();return}const checks=event.target.closest('[data-authoring-checks]');if(checks){event.stopImmediatePropagation();draft.checks=checks.value.split('\n').filter(x=>x.trim()).map(line=>{const [label,lhs,rhs]=line.split('|').map(x=>x.trim());return {label:label||'',lhs:lhs||'',rhs:rhs||''}});authoringPersistLocal();return}}
 const materialField=event.target.closest('[data-material-property]');
 if(materialField&&state.exam){
  event.stopImmediatePropagation();const card=state.exam.cards[state.card],blocks=uxEnsureMaterials(card),block=blocks.find(item=>item.id===materialField.dataset.materialId);if(!block)return;
  const property=materialField.dataset.materialProperty,oldKind=block.kind,value=materialField.value;
  if(property==='kind'){
   if(!['image','text','table'].includes(value))return;block.kind=value;
   if(value==='image'){const defaults=uxImageDefaults();for(const [key,defaultValue] of Object.entries(defaults))if(!(key in block))block[key]=uxClone(defaultValue);uxState.materialByCard[card.id]=block.id}
  }else if(property==='content')block.content=value;else if(property==='label')block.label=value;
  uxSyncMaterialAliases(card);uxState.lastField=property==='content'?'material':'materials';
  uxTouchMaterialEdit(card,{imageContext:property==='content'&&block.kind==='image'||property==='kind'&&(oldKind==='image'||value==='image')?block:null});
  if($('#previewSheet')){$('#previewSheet').innerHTML=preview(current());renderPreviewMath()}
  if(property==='kind')requestAnimationFrame(()=>render());
  return;
 }
 const el=event.target.closest('[data-field]');if(!el||!state.exam)return;
 const c=current(),key=el.dataset.field;c[key]=el.value;uxState.lastField=key;
 if(key==='data_kind'&&c.data_kind!=='image'&&uxState.tab==='plan')uxState.tab='question';
 if(['image_mode','image_locked','image_creative','image_text_physics','image_text_math','image_text_korean','material','stem','question','choices','statements','data_kind'].includes(key)){c.image_plan_approval=null;if(c.image&&['stem','material','question','choices','statements','data_kind'].includes(key))c.image.approved=false}
 if(key==='image_mode'){
  if(el.value==='strict')c.image_creative='';if(el.value==='flexible')c.image_locked='';c.image_plan_version=2;
  for(const [name,hide] of [['image_locked',el.value==='flexible'],['image_creative',el.value==='strict']]){const field=document.querySelector(`[data-field="${name}"]`);if(field){field.value=c[name]||'';field.closest('label').hidden=hide}}
  const hint=$('#imageModeHint');if(hint)hint.textContent=modeDescription(el.value);
 }
 if(key==='image_text_physics'||key==='image_text_math'||key==='image_text_korean')c.image_plan_version=2;
 markDirty(key!=='ai_feedback');
 if(key==='standard'){const found=state.standards[el.value];c.standard_name=found?.name||'';c.standard_note=found?.note||'';$('#standardName').textContent=found?.name||'과목의 성취기준인지 확인해 주세요.'}
 if($('#previewSheet')){$('#previewSheet').innerHTML=preview(c);renderPreviewMath()}
 if(key==='data_kind')requestAnimationFrame(()=>render());
},true);
document.addEventListener('change',event=>{
 const authoringForm=event.target.closest('#authoringDraftForm'),session=state.authoringDraft;if(authoringForm&&session?.mode){const requestKind=event.target.closest('[data-authoring-request-kind]');if(requestKind){event.stopImmediatePropagation();authoringSetRequestKinds(session.draft,[...authoringForm.querySelectorAll('[data-authoring-request-kind]:checked')].map(input=>input.dataset.authoringRequestKind));authoringSyncRequestImageMode(authoringForm,session.draft);authoringPersistLocal();return}const bool=event.target.closest('[data-authoring-bool]');if(bool){event.stopImmediatePropagation();session.draft[bool.dataset.authoringBool]=bool.checked;authoringPersistLocal();return}const field=event.target.closest('[data-authoring-field]');if(field&&field.tagName==='SELECT'){event.stopImmediatePropagation();field.dispatchEvent(new Event('input',{bubbles:true}));return}}
 const bulkImage=event.target.closest('[data-bulk-image]');if(bulkImage){event.stopImmediatePropagation();const id=bulkImage.dataset.bulkImage;if(bulkImage.checked)uxState.bulkImageIds.add(id);else uxState.bulkImageIds.delete(id);uxUpdateBulkImageBar();return}
 const request=event.target.closest('[data-ai-request]');if(request){event.stopImmediatePropagation();const c=state.exam.cards.find(item=>item.id===request.dataset.aiRequest);if(c){c.ai_requested=request.checked;request.value=request.checked?'yes':'no';markDirty(false);renderStats();const label=request.closest('.ai-check');if(label)label.classList.toggle('is-checked',request.checked)}return}
 const bool=event.target.closest('[data-bool]');if(bool){event.stopImmediatePropagation();const key=bool.dataset.bool,c=current();if(key==='image_text_none'&&bool.checked&&(c.image_text_physics||c.image_text_math||c.image_text_korean||c.image_labels?.length)){bool.checked=false;toast('글씨 없음은 세 글씨 칸과 글씨 객체가 비어 있을 때 선택할 수 있습니다.');return}c[key]=bool.checked;uxState.lastField=key;markDirty();return}
 const materialSelect=event.target.closest('[data-material-property="kind"]');if(materialSelect){materialSelect.dispatchEvent(new Event('input',{bubbles:true}));return}
 const select=event.target.closest('[data-field]');if(select){select.dispatchEvent(new Event('input',{bubbles:true}))}
},true);
document.addEventListener('input',event=>{
 if(event.target.id==='checksInput'&&state.exam){current().checks=event.target.value.split('\n').filter(x=>x.trim()).map(line=>{const [label,lhs,rhs]=line.split('|').map(x=>x.trim());return {label:label||'',lhs:lhs||'',rhs:rhs||''}});markDirty()}
},true);
uxState.rowActionPointerDown=false;
document.addEventListener('pointerdown',event=>{uxState.rowActionPointerDown=!!event.target.closest('.row-actions')},true);
document.addEventListener('pointerup',()=>{setTimeout(()=>{uxState.rowActionPointerDown=false},0)},true);
document.addEventListener('pointercancel',()=>{uxState.rowActionPointerDown=false},true);
document.addEventListener('dragstart',event=>{if(!uxState.rowActionPointerDown)return;event.preventDefault();event.stopImmediatePropagation();uxState.rowActionPointerDown=false},true);
document.addEventListener('click',event=>{
 const session=state.authoringDraft,active=!!session?.mode&&!session.suspended,nav=event.target.closest('[data-stage],[data-ux-action="home"],[data-ux-action="new-exam"],#workspaceHome,#newExam,[data-open-exam]');if(active&&nav){event.preventDefault();event.stopImmediatePropagation();toast('문항을 저장하거나 목록으로 돌아간 뒤 이동해 주세요.');return}
 const choice=event.target.closest('[data-authoring-choice]');if(choice){event.preventDefault();event.stopImmediatePropagation();authoringChoose(choice.dataset.authoringChoice);return}
 if(event.target.closest('[data-authoring-cancel]')){event.preventDefault();event.stopImmediatePropagation();authoringCancel();return}
 if(event.target.closest('[data-authoring-resume]')){event.preventDefault();event.stopImmediatePropagation();if(session){session.suspended=false;authoringPersistLocal();render();document.querySelector('#authoringDraftForm [data-authoring-field="standard"]')?.focus({preventScroll:true})}return}
 if(event.target.closest('[data-authoring-discard]')){event.preventDefault();event.stopImmediatePropagation();authoringDiscard();return}
 if(event.target.closest('#addCard')||event.target.closest('[data-ux-action="add-card"]')){event.preventDefault();event.stopImmediatePropagation();authoringOpenChoice();return}
  const rowDuplicate=event.target.closest('[data-duplicate-card-id]');if(rowDuplicate&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(()=>uxDuplicateCardById(rowDuplicate.dataset.duplicateCardId));return}
  const rowDelete=event.target.closest('[data-remove-card-id]');if(rowDelete&&state.exam){event.preventDefault();event.stopImmediatePropagation();uxOpenCardDeleteDialog(rowDelete.dataset.removeCardId,rowDelete);return}
  const row=event.target.closest('[data-card]');if(row&&state.exam&&state.stage===0&&!event.target.closest('[data-ai-request]')&&!event.target.closest('.row-actions')){const card=state.exam.cards[Number(row.dataset.card)],hasQuestion=String(card?.question||'').trim();if(card&&(!hasQuestion&&authoringAiPending(card)||card.authoring_mode==='manual'&&!hasQuestion)){event.preventDefault();event.stopImmediatePropagation();authoringStart(authoringAiPending(card)?'ai':'manual',card.id);return}}
 if(event.target.closest('#authoringDraftForm')&&event.target.closest('[data-material-add]')){event.preventDefault();event.stopImmediatePropagation();const draft=session.draft,blocks=uxEnsureMaterials(draft),kind=event.target.closest('[data-material-add]').dataset.materialAdd,imageCount=blocks.filter(block=>block.kind==='image').length,block={id:uxMakeId(),kind,label:kind==='image'?uxImageLabel(imageCount):kind==='table'?'표':'글상자',content:'',...(kind==='image'?uxImageDefaults():{})};blocks.push(block);uxSyncMaterialAliases(draft);authoringPersistLocal();render();return}
 if(event.target.closest('#authoringDraftForm')&&event.target.closest('[data-material-remove]')){event.preventDefault();event.stopImmediatePropagation();const draft=session.draft,id=event.target.closest('[data-material-remove]').dataset.materialRemove;draft.materials=uxEnsureMaterials(draft).filter(block=>block.id!==id);uxSyncMaterialAliases(draft);authoringPersistLocal();render();return}
 if(event.target.closest('#authoringDraftForm')&&event.target.closest('[data-material-move]')){event.preventDefault();event.stopImmediatePropagation();const draft=session.draft,button=event.target.closest('[data-material-move]'),blocks=uxEnsureMaterials(draft),from=blocks.findIndex(block=>block.id===button.dataset.materialId),to=from+Number(button.dataset.materialMove);if(from>=0&&to>=0&&to<blocks.length){blocks.splice(to,0,blocks.splice(from,1)[0]);uxSyncMaterialAliases(draft);authoringPersistLocal();render()}return}
 if(event.target.closest('#authoringDraftForm')&&event.target.closest('[data-plan-material]')){event.preventDefault();event.stopImmediatePropagation();toast('문항을 저장한 뒤 검토 단계에서 그림 계획을 편집할 수 있습니다.');return}
 const addMaterial=event.target.closest('[data-material-add]');
 if(addMaterial&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const card=state.exam.cards[state.card],block=uxAddMaterial(card,addMaterial.dataset.materialAdd);uxState.tab='question';uxTouchMaterialEdit(card,{imageContext:block.kind==='image'?block:null});render();await save();toast(`${block.label||'자료'}를 추가했습니다. 필요한 자료를 더 추가할 수 있습니다.`)});return}
 const convertMaterials=event.target.closest('[data-material-convert]');
 if(convertMaterials&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const card=state.exam.cards[state.card],blocks=uxEnsureMaterials(card);uxSyncMaterialAliases(card);uxTouchMaterialEdit(card);render();await save();toast(`${blocks.length}개 자료를 이름·순서 편집 목록으로 옮겼습니다.`)});return}
 const materialRemove=event.target.closest('[data-material-remove]');
 if(materialRemove&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const card=state.exam.cards[state.card];uxEnsureMaterials(card);const id=materialRemove.dataset.materialRemove;card.materials=card.materials.filter(block=>block.id!==id);if(uxState.materialByCard[card.id]===id)delete uxState.materialByCard[card.id];uxSyncMaterialAliases(card);uxTouchMaterialEdit(card);render();await save()});return}
 const materialMove=event.target.closest('[data-material-move]');
 if(materialMove&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const card=state.exam.cards[state.card];uxEnsureMaterials(card);const from=card.materials.findIndex(block=>block.id===materialMove.dataset.materialId),to=from+Number(materialMove.dataset.materialMove);if(from<0||to<0||to>=card.materials.length)return;card.materials.splice(to,0,card.materials.splice(from,1)[0]);uxSyncMaterialAliases(card);uxTouchMaterialEdit(card);render();await save()});return}
 const planMaterial=event.target.closest('[data-plan-material]');
 if(planMaterial&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{const id=state.exam.cards[state.card].id;await save();const card=state.exam.cards.find(item=>item.id===id);uxSelectMaterial(card,planMaterial.dataset.planMaterial,{preferImage:true});state.stage=1;uxState.tab='plan';render();document.querySelector('[data-review-tab="plan"]')?.focus({preventScroll:true})});return}
 const imageMaterial=event.target.closest('[data-image-material]');
 if(imageMaterial&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{const id=state.exam.cards[state.card].id;await save();const card=state.exam.cards.find(item=>item.id===id);uxSelectMaterial(card,imageMaterial.dataset.imageMaterial,{preferImage:true});state.stage=2;imageFlowState().step=uxImageStepForMaterial(uxActiveImageBlock(card));render();$('#imageFlowHeading')?.focus({preventScroll:true})});return}
 const removeCard=event.target.closest('#removeCard');if(removeCard&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{
  await save();if(state.exam.cards.length<=1)throw Error('최소 한 문항은 남겨 주세요.');uxStoreImageToolState();
  const removed=state.exam.cards[state.card]?.id;state.exam.cards=state.exam.cards.filter(c=>c.id!==removed).map((c,i)=>({...c,no:i+1}));state.card=Math.max(0,Math.min(state.card,state.exam.cards.length-1));state.exam.card_approval=null;markDirty(false);await save();render();
 });return}
 if(event.target.closest('#uxBulkSelectAll')){event.preventDefault();event.stopImmediatePropagation();uxSyncBulkImages();for(const card of state.exam.cards)if(uxImageMaterials(card).length)uxState.bulkImageIds.add(card.id);uxUpdateBulkImageBar();return}
 if(event.target.closest('#uxBulkClearSelection')){event.preventDefault();event.stopImmediatePropagation();uxState.bulkImageIds.clear();uxUpdateBulkImageBar();return}
 if(event.target.closest('[data-ux-job-log]')){event.preventDefault();event.stopImmediatePropagation();const job=state.job;if(!job)return;$('#jobLog').textContent=(job.failed?.length?job.failed.map(x=>`${x.no}번 실패: ${x.error}`).join('\n')+'\n\n':'')+(job.log||job.message||'작업 기록이 없습니다.');$('#logDialog').showModal();return}
 if(event.target.closest('[data-ux-job-dismiss]')){event.preventDefault();event.stopImmediatePropagation();state.job=null;$('#jobBanner').hidden=true;render();return}
 const tab=event.target.closest('[data-review-tab]');if(tab){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();uxSetTab(tab.dataset.reviewTab)});return}
 const issue=event.target.closest('[data-issue-stage]');if(issue){event.preventDefault();event.stopImmediatePropagation();uxIssueTarget(issue);return}
 const actionButton=event.target.closest('[data-ux-action]');if(actionButton){event.preventDefault();event.stopImmediatePropagation();action(async()=>{
  const type=actionButton.dataset.uxAction;
   if(type==='new-exam'){uxNewExam();return}if(type==='rewrite-current'){const cardId=current().id,feedback=$('[data-field="ai_feedback"]')?.value||current().ai_feedback||'';await save();const card=state.exam.cards.find(item=>item.id===cardId);if(!card)throw Error('현재 문항을 찾을 수 없습니다.');card.ai_requested=true;markDirty(false);await save();const job=await api('/api/jobs',{exam_id:state.exam.id,card_id:card.id,action:'question',feedback,provider:state.provider,model:state.model});state.job=job;watch(job.id);return}if(type==='home'){await save();state.exam=null;state.job=null;state.stage=0;state.card=0;state.boot=await api('/api/bootstrap');renderSidebar();render();return}
  if(type==='resolve-save'){if(uxState.conflict){uxRenderConflict();return}await save();if(!state.dirty){uxSetSaveStatus('saved');const holder=$('#saveProblem');if(holder){holder.hidden=true;holder.innerHTML=''}}return}
  if(type==='start-review'){await save();const next=state.exam.cards.find(card=>!card.review_approved);if(next)uxSetCurrentById(next.id);state.stage=1;uxState.tab='question';render();return}
  if(type==='connect'){$('#settingsBtn').click();return}if(type==='add-card'){await addCard();uxPersistLocation();return}
  if(type==='missing-design'){authoringStart('ai',actionButton.dataset.cardId);return}
  if(type==='next-review'){await save();uxSetCurrentById(actionButton.dataset.cardId);state.stage=1;uxState.tab='question';render();return}
  if(type==='generate-questions'){await uxGenerateQuestionIds(state.exam.cards.filter(authoringAiPending).map(c=>c.id));return}
  if(type==='generate-images'){const ids=[...uxState.bulkImageIds].filter(id=>state.exam.cards.some(c=>c.id===id&&uxImageMaterials(c).length));if(!ids.length)throw Error('그림 목록에서 생성할 문항을 선택해 주세요.');await save();if(!state.exam.card_approval)throw Error('문항카드 전체 승인 후 선택한 그림을 생성할 수 있습니다.');let missing=null,missingCardId=null;for(const id of ids){const card=state.exam.cards.find(item=>item.id===id);missing=uxImageMaterials(card).find(block=>!block.image_plan_approval);if(missing){missingCardId=id;break}}if(missing){uxSetCurrentById(missingCardId);const card=state.exam.cards[state.card];uxState.materialByCard[card.id]=missing.id;state.stage=2;imageFlowState().step=0;render();toast(`${card.no}번 ${missing.label||'그림'} 계획은 저장됐습니다. 계획 확인을 눌러 주세요.`);return}const job=await api('/api/jobs',{exam_id:state.exam.id,action:'image',card_ids:ids,provider:state.provider,model:state.model});state.job=job;watch(job.id);return}
  if(type==='retry-questions'){const ids=(actionButton.dataset.cardIds||'').split(',').filter(id=>state.exam.cards.some(c=>c.id===id&&authoringAiPending(c)));if(!ids.length)throw Error('다시 생성할 Yes 문항이 없습니다.');await uxGenerateQuestionIds(ids);return}
  if(type==='review-current'){await save();const card=current(),approved=await uxApproveWithDiscrepancy(card,'question');if(!approved)return;state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);state.dirty=false;uxRemoveDraft(state.exam.id);const next=state.exam.cards.find(x=>!x.review_approved);if(next)uxSetCurrentById(next.id);render();if(!next)uxReviewSummary();return}
  if(type==='show-approval-summary'){await save();state.exam=await api('/api/exams/'+state.exam.id);uxReviewSummary();return}
  if(type==='approve-exam'){await save();state.exam=await api('/api/exams/'+state.exam.id);uxReviewSummary();return}
  if(type==='go-images'||type==='go-review'||type==='go-export'){await save();state.stage=type==='go-images'?2:type==='go-review'?1:3;if(state.stage===2&&!state.exam.card_approval)state.stage=1;if(state.stage===3)state.exam=await api('/api/exams/'+state.exam.id);render();return}
  if(type==='edit-image-plan'){await save();state.stage=1;uxState.tab='plan';render();requestAnimationFrame(()=>document.querySelector('[data-review-tab="plan"]')?.focus({preventScroll:true}));return}
  if(type==='confirm-plan'){await save();await api('/api/confirm-image-plan',{exam_id:state.exam.id,card_id:current().id});state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);const block=uxActiveImageBlock(state.exam.cards[state.card]);imageFlowState().step=block?.image?(block.image.approved||block.labels_initialized?3:2):1;render();return}
  if(type==='generate-image'){await generate('image');return}
  if(type==='retry-labels'){await save();const job=await api('/api/jobs',{exam_id:state.exam.id,card_id:current().id,action:'labels',provider:state.provider,model:state.model});state.job=job;watch(job.id);return}
  if(type==='save-image-edit'){await save();ve.expanded=false;imageFlowState().step=3;render();$('#imageFlowHeading')?.focus({preventScroll:true});return}
  if(type==='approve-image'){await save();const card=current(),block=uxActiveImageBlock(card),approved=await uxApproveWithDiscrepancy(card,'image',block?.id);if(!approved)return;state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);state.dirty=false;imageFlowState().step=3;render();return}
  if(type==='next-image'){
   await save();const target=uxNextUnapprovedImage(state.card,uxActiveImageBlock(state.exam.cards[state.card])?.id);
   if(!target){state.stage=3;state.exam=await api('/api/exams/'+state.exam.id)}else{uxClearMaterialTools();state.card=target.cardIndex;uxState.materialByCard[target.card.id]=target.block.id;state.stage=2;imageFlowState().step=uxImageStepForMaterial(target.block)}render();return
  }
  if(type==='first-output-issue'){await save();state.exam=await api('/api/exams/'+state.exam.id);render();const btn=document.querySelector('.issue-link');if(btn)uxIssueTarget(btn);return}
  if(type==='create-export'){await save();state.exam=await api('/api/export',{exam_id:state.exam.id});state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);state.dirty=false;render();toast('시험지와 정답·해설을 만들었습니다.');return}
 });return}
 if(event.target.closest('#openScorePanel')){event.preventDefault();event.stopImmediatePropagation();uxOpenScorePanel();return}
 if(event.target.closest('#newExamAction')){event.preventDefault();event.stopImmediatePropagation();uxNewExam();return}
 const retry=event.target.closest('[data-ux-retry-save]');if(retry){event.preventDefault();event.stopImmediatePropagation();save().catch(uxShowSaveError);return}
 const dismissSave=event.target.closest('[data-ux-dismiss-save-problem]');if(dismissSave){event.preventDefault();event.stopImmediatePropagation();const holder=$('#saveProblem');holder.hidden=true;holder.innerHTML='';return}
 if(event.target.closest('#saveBtn')){event.preventDefault();event.stopImmediatePropagation();save().then(()=>toast('저장했습니다.')).catch(uxShowSaveError);return}
 const stage=event.target.closest('[data-stage]');if(stage&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{
  await save();const target=Number(stage.dataset.stage);if(target===2&&!state.exam.card_approval)throw Error('출제안 승인 후 그림 단계를 열 수 있습니다.');
  state.stage=target;if(target===3)state.exam=await api('/api/exams/'+state.exam.id);render();
 });return}
   if(event.target.closest('[data-reorder-handle]'))return;const select=event.target.closest('[data-card],[data-select]');if(select&&state.exam&&!event.target.closest('[data-ai-request]')&&!event.target.closest('.row-actions')){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const i=Number(select.dataset.card??select.dataset.select);if(!Number.isInteger(i)||!state.exam.cards[i])return;const openCriteria=select.dataset.card!==undefined&&state.stage===0,card=state.exam.cards[i],hasQuestion=String(card.question||'').trim();if(openCriteria&&(!hasQuestion&&authoringAiPending(card)||card.authoring_mode==='manual'&&!hasQuestion)){authoringStart(authoringAiPending(card)?'ai':'manual',card.id);return}uxStoreImageToolState();state.card=i;if(select.dataset.card!==undefined)state.stage=1;render();if(openCriteria)document.querySelector('.criteria-panel')?.setAttribute('open','')});return}
},true);
document.addEventListener('click',event=>{
 const imageStep=event.target.closest('[data-image-step]');if(imageStep&&state.exam){event.preventDefault();event.stopImmediatePropagation();action(async()=>{await save();const step=Number(imageStep.dataset.imageStep);if(!imageFlowAllowed(step))throw Error('앞 단계의 확인을 먼저 완료해 주세요.');imageFlowState().step=step;render()});return}
 const next=event.target.closest('[data-image-next-card]');if(next){event.preventDefault();event.stopImmediatePropagation();document.querySelector('[data-ux-action=next-image]')?.click()}
},true);
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-recalc]');if(button){event.preventDefault();event.stopImmediatePropagation();if(!state.boot.hwp_conversion_available){toast('한글과 pyhwpx를 사용할 수 있는 PC에서만 HWP 변환을 할 수 있습니다.');return}action(async()=>{await save();await api('/api/recalculate',{exam_id:state.exam.id,export_id:button.dataset.recalc});state.exam=await api('/api/exams/'+state.exam.id);uxBaseExam.value=uxClone(state.exam);state.dirty=false;render();toast('HWP 변환을 마쳤습니다. 실제 인쇄 배치는 한글에서 확인해 주세요.')})}
},true);
function uxBindDelete(){const b=$('#deleteExam');if(b)b.onclick=()=>{if(state.job?.status==='running')throw Error('진행 중인 작업을 먼저 완료하거나 취소해 주세요.');$('#deleteTitle').textContent=state.exam.title;$('#deleteDialog').showModal()}}
$('#sidebarToggle').setAttribute('aria-expanded','false');$('#sidebarToggle').setAttribute('aria-label','작업실 목록 펼치기');document.body.classList.add('sidebar-collapsed');
$('#sidebarToggle').onclick=()=>{const open=document.body.classList.toggle('sidebar-collapsed')===false;$('#sidebarToggle').setAttribute('aria-expanded',String(open));$('#sidebarToggle').setAttribute('aria-label',open?'작업실 목록 접기':'작업실 목록 펼치기')};
$('#workspaceHome').onclick=()=>action(async()=>{await save();state.exam=null;state.job=null;state.stage=0;state.card=0;state.boot=await api('/api/bootstrap');renderSidebar();render()});
$('#newExam').onclick=uxNewExam;$('#settingsBtn').classList.add('settings-in-menu');
$('#confirmDelete').onclick=()=>action(async()=>{const exam=state.exam;if(!exam)return;await api('/api/delete',{exam_id:exam.id,confirm_title:exam.title});uxRemoveDraft(exam.id);try{localStorage.removeItem(uxLocationKey(exam.id));if(localStorage.getItem('qm-last-exam')===exam.id)localStorage.removeItem('qm-last-exam')}catch{}$('#deleteDialog').close();state.exam=null;state.job=null;state.dirty=false;state.stage=0;state.card=0;$('#jobBanner').hidden=true;state.boot=await api('/api/bootstrap');renderSidebar();render();toast('작업실을 삭제했습니다. 기존 엑셀 원본은 유지됩니다.')});
window.addEventListener('beforeunload',event=>{if(state.authoringDraft?.mode&&!state.authoringDraft.suspended){authoringPersistLocal();event.preventDefault();event.returnValue=''}if(state.dirty){uxWriteDraft();event.preventDefault();event.returnValue=''}});
// Compare a local draft with the latest server copy; only overlapping edits require a choice.
function uxJsonEqual(a,b){return JSON.stringify(a)===JSON.stringify(b)}
function uxThreeWayMerge(base,local,remote,choices={}){
 const merged=uxClone(remote),conflicts=[];if(!base){const chosen=choices.whole==='local'?uxClone(local):uxClone(remote),remoteCards=new Map((remote.cards||[]).map(c=>[c.id,c]));for(const c of chosen.cards||[]){const saved=remoteCards.get(c.id);if(saved)c.calculation_override=uxClone(saved.calculation_override??null)}chosen.exports=uxClone(remote.exports||[]);chosen.card_approval=uxClone(remote.card_approval);chosen.revision=remote.revision;chosen.updated=remote.updated;return {merged:chosen,conflicts:[{path:'전체 시험',base:null,local,remote,choiceKey:'whole'}]}}
 const choose=(path,b,l,r,key)=>{const localChanged=!uxJsonEqual(b,l),remoteChanged=!uxJsonEqual(b,r);if(!localChanged)return r;if(!remoteChanged||uxJsonEqual(l,r))return l;conflicts.push({path,base:b,local:l,remote:r,choiceKey:key});return choices[key]==='local'?l:r};
 for(const key of ['title','subject'])merged[key]=choose(key,base[key],local[key],remote[key],key);
 const baseCards=new Map((base.cards||[]).map(c=>[c.id,c])),localCards=new Map((local.cards||[]).map(c=>[c.id,c])),remoteCards=new Map((remote.cards||[]).map(c=>[c.id,c])),resultCards=new Map();
 const ignored=new Set(['no','review_approved','image_plan_approval','image','calculation_override']);
 for(const id of new Set([...baseCards.keys(),...localCards.keys(),...remoteCards.keys()])){
  const b=baseCards.get(id),l=localCards.get(id),r=remoteCards.get(id);
  if(!b){const chosen=choose(`문항 ${id} 추가`,undefined,l,r,`card:${id}:exist`);if(chosen)resultCards.set(id,uxClone(chosen));continue}
  if(!l||!r){const value=choose(`문항 ${b.no} 삭제/수정`,b,l,r,`card:${id}:exist`);if(value)resultCards.set(id,uxClone(value));continue}
  const out=uxClone(r);for(const key of new Set([...Object.keys(b),...Object.keys(l),...Object.keys(r)])){if(ignored.has(key))continue;out[key]=choose(`문항 ${b.no} · ${key}`,b[key],l[key],r[key],`card:${id}:${key}`)}
  resultCards.set(id,out);
 }
 const baseOrder=(base.cards||[]).map(c=>c.id),localOrder=(local.cards||[]).map(c=>c.id),remoteOrder=(remote.cards||[]).map(c=>c.id);
 const order=choose('문항 순서',baseOrder,localOrder,remoteOrder,'cards:order').filter(id=>resultCards.has(id));
 for(const id of resultCards.keys())if(!order.includes(id))order.push(id);
 merged.cards=order.map((id,index)=>({...resultCards.get(id),id,no:index+1}));
 merged.exports=uxClone(remote.exports||[]);merged.card_approval=uxClone(remote.card_approval);merged.revision=remote.revision;merged.updated=remote.updated;
 return {merged,conflicts};
}
function uxFormatConflict(value){const text=value===undefined?'(없음)':typeof value==='string'?value:JSON.stringify(value,null,2);return esc(text.length>800?text.slice(0,800)+'…':text)}
function uxRenderConflict(choices={}){
 const conflict=uxState.conflict,dialog=$('#conflictDialog');if(!conflict||!dialog)return;
 const result=uxThreeWayMerge(conflict.base,conflict.local,conflict.remote,choices);uxState.pendingMerge=result;
 const conflicts=result.conflicts;
 dialog.innerHTML=`<div class="dialog-top"><div><div class="eyebrow">저장 충돌 · 초안 보존됨</div><h2>최신 저장본과 내 초안을 비교하세요</h2></div><button class="icon-btn" data-close="conflictDialog" aria-label="닫기">×</button></div><p class="conflict-meta">최신본 revision ${conflict.remote.revision} · 초안 기준 ${conflict.base?.revision??'확인 불가'} · 내 수정 내용은 이 브라우저에 보존되어 있습니다.</p><div class="conflict-summary"><b>내 변경 ${conflict.local.cards?.length||0}문항 · 최신 저장본 ${conflict.remote.cards?.length||0}문항</b><button id="downloadDraft">내 초안 JSON 받기</button></div>${conflicts.length?`<div class="conflict-list"><h3>겹친 변경 ${conflicts.length}개</h3>${conflicts.map(item=>`<fieldset class="conflict-item"><legend>${esc(item.path)}</legend><label><input type="radio" name="${esc(item.choiceKey)}" value="remote" ${choices[item.choiceKey]!=='local'?'checked':''}><span>최신 저장본</span><pre>${uxFormatConflict(item.remote)}</pre></label><label><input type="radio" name="${esc(item.choiceKey)}" value="local" ${choices[item.choiceKey]==='local'?'checked':''}><span>내 초안</span><pre>${uxFormatConflict(item.local)}</pre></label></fieldset>`).join('')}</div>`:'<div class="notice">수정한 항목이 겹치지 않습니다. 내 변경을 최신본에 합칠 수 있습니다.</div>'}<p>겹치지 않은 내 수정은 최신본에 자동으로 이어 붙입니다. 저장 뒤에는 두 변경이 하나의 새 버전으로 기록됩니다.</p><div class="dialog-actions"><button id="reloadLatest">최신 저장본 열기</button><button id="applyMergedDraft" class="primary">${conflicts.length?'선택을 적용하고 저장':'내 변경을 합쳐 저장'}</button></div>`;
 if(!dialog.open)dialog.showModal();
 $('#downloadDraft').onclick=()=>{const blob=new Blob([JSON.stringify(conflict.local,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${conflict.local.title||'시험'}-초안.json`;a.click();URL.revokeObjectURL(a.href)};
 $('#reloadLatest').onclick=()=>action(async()=>{const id=conflict.remote.id;state.exam=uxClone(conflict.remote);state.dirty=false;uxBaseExam.value=uxClone(conflict.remote);uxState.conflict=null;uxRemoveDraft(id);state.card=Math.min(state.card,state.exam.cards.length-1);$('#conflictDialog').close();render()});
 $('#applyMergedDraft').onclick=()=>action(async()=>{
  const nextChoices={};dialog.querySelectorAll('input[type=radio]:checked').forEach(input=>{nextChoices[input.name]=input.value});
  if(!conflict.base&&nextChoices.whole==='remote'){const id=conflict.remote.id;state.exam=await api('/api/exams/'+id);state.dirty=false;uxBaseExam.value=uxClone(state.exam);uxState.conflict=null;uxRemoveDraft(id);$('#conflictDialog').close();render();return}
  const merged=uxThreeWayMerge(conflict.base,conflict.local,conflict.remote,nextChoices).merged;
  state.exam=merged;state.exam.revision=conflict.remote.revision;uxBaseExam.value=uxClone(conflict.remote);uxState.conflict=null;state.dirty=true;uxState.version++;
  const active=state.exam.cards.findIndex(c=>c.id===uxReadDraft(conflict.remote.id)?.card_id);if(active>=0)state.card=active;
  $('#conflictDialog').close();uxWriteDraft();await save();render();
 });
}
document.addEventListener('change',event=>{
 const choice=event.target.closest('.conflict-item input[type=radio]');if(!choice||!uxState.conflict)return;
 const selections={};document.querySelectorAll('.conflict-item input[type=radio]:checked').forEach(input=>selections[input.name]=input.value);uxRenderConflict(selections);
},true);
document.addEventListener('click',event=>{
 if(event.target.closest('[data-close]')){const dialog=$('#'+event.target.closest('[data-close]').dataset.close);dialog?.close();return}
 if(event.target.closest('#teacherHelpBtn')){
  event.preventDefault();event.stopImmediatePropagation();
  const details=teacherHelpSections.map(([q,a],i)=>`<details ${i===(state.stage===0?0:state.stage===1?2:state.stage===2?3:5)?'open':''}><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('');$('#teacherHelpBody').innerHTML=`<p class="help-context">${['설계에서 출제 범위와 AI 요청을 정합니다.','검토에서 문항과 정답·해설을 확인합니다.','그림에서 계획, 생성, 편집, 확정을 진행합니다.','출력에서 누락을 해결하고 파일을 받습니다.'][state.stage]||'새 시험 제목과 과목을 선택하세요.'}</p>${details}`;if(!$('#teacherHelpDialog').open)$('#teacherHelpDialog').showModal();return;
 }
},true);
document.addEventListener('keydown',event=>{
 if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'&&state.exam){event.preventDefault();save().then(()=>toast('저장했습니다.')).catch(uxShowSaveError)}
});
const uxOriginalBoot=boot;
boot=async function(){
 await uxOriginalBoot();const last=localStorage.getItem('qm-last-exam');
 if(last&&state.boot.exams.some(x=>x.id===last))await uxOpenExam(last);
 else{renderSidebar();render()}
};
action(boot);
Object.defineProperty(window,'__uxMinimalReady',{value:true});

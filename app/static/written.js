'use strict';
// 서답형(단답형·서술형·논술형) 카드와 시험지 머리말 설정. 서답형은 선택형 뒤에 "서답형 1."로 따로 번호를 매겨 인쇄한다.
function isSubjective(card){return (state.boot?.subjective_types||[]).includes(card?.type)}
function writtenOrder(card){const list=(state.exam?.cards||[]).filter(isSubjective);return list.findIndex(c=>c.id===card.id)+1}
function printedNumber(card){return isSubjective(card)?`서답형 ${writtenOrder(card)||''}.`:`${card.no}.`}
function printedPoints(card){
 if(!card.points)return isSubjective(card)?`[${esc(card.type)}]`:'';
 return isSubjective(card)?`<b>[${esc(card.type)}-${Number(card.points).toFixed(1)}점${card.partial_credit?', 부분점수 있음.':''}]</b>`:`[${esc(card.points)}점]`;
}
// tools/gen.py split_question 과 같다: 발문 칸의 상황 설명과 묻는 문장은 줄을 나눠 인쇄한다.
function splitQuestion(text){
 const found=[...text.matchAll(/다\.\s+/g)].pop();
 if(!found||!/(\?|시오\.)\s*$/.test(text))return ['',text];
 return [text.slice(0,found.index+2).trim(),text.slice(found.index+found[0].length).trim()];
}
function writtenReviewFields(field,card){
 return `${field('model_answer','모범 답안',{full:true,textarea:true,tall:true})}${field('rubric','채점 기준 · 요소별 배점과 감점',{full:true,textarea:true,tall:true})}<label class="check-row full"><input type="checkbox" data-written-partial ${card.partial_credit?'checked':''}>부분 점수 있음 (시험지에 표시)</label>`;
}
function writtenAuthoringFields(draft){
 return `<label class="full">답안 조건 · 줄마다 하나씩<textarea data-authoring-field="conditions" placeholder="예: 답안은 ‘~(이)다’로 끝나게 작성합니다.">${esc(draft.conditions||'')}</textarea></label><label class="full">모범 답안<textarea class="tall" data-authoring-field="model_answer">${esc(draft.model_answer||'')}</textarea></label><label class="full">채점 기준 · 요소별 배점과 감점<textarea class="tall" data-authoring-field="rubric">${esc(draft.rubric||'')}</textarea></label>`;
}
function paperSettings(exam){
 let remembered='';try{remembered=localStorage.getItem('qm-school')||''}catch{}
 const school=exam.school||remembered;
 if(!exam.school&&remembered)queueMicrotask(()=>{if(state.exam===exam&&!exam.school){exam.school=remembered;markDirty(false)}});
 return `<section class="paper-settings"><h3>시험지 머리말</h3><div class="paper-settings-row"><label>학교명<input data-exam-field="school" maxlength="40" value="${esc(school)}" placeholder="비우면 학교명 없이 인쇄합니다"></label><label>지문 글자 크기<select data-exam-field="passage_size">${[['11','11pt (기본)'],['10.5','10.5pt'],['10','10pt']].map(([v,l])=>`<option value="${v}" ${String(exam.passage_size||'11')===v?'selected':''}>${l}</option>`).join('')}</select></label></div><p class="hint">B4 2단 양식으로 인쇄합니다. 학교명은 머리말과 마지막 쪽 지적소유권 표에 들어가고, 지문 글자 크기는 지문 세트에 적용됩니다.</p></section>`;
}
document.addEventListener('change',event=>{
 const setting=event.target.closest('[data-exam-field]');
 if(setting&&state.exam){
  state.exam[setting.dataset.examField]=setting.value.trim();
  if(setting.dataset.examField==='school')try{localStorage.setItem('qm-school',setting.value.trim())}catch{}
  markDirty(false);return;
 }
 const partial=event.target.closest('[data-written-partial]');
 if(partial&&current()){current().partial_credit=partial.checked;markDirty(true);render();return}
});
// 직접 작성 중 선택형↔서답형으로 바뀌면 입력 칸이 달라진다. 초안 저장 처리가 이벤트를 먼저 끝내므로 창 단계에서 본다.
window.addEventListener('change',event=>{
 const kind=event.target.closest?.('[data-authoring-field="type"]'),session=state.authoringDraft;
 if(!kind||session?.mode!=='manual'||!session.draft)return;
 session.draft.type=kind.value;
 const drawn=!!kind.form?.querySelector('[data-authoring-field="model_answer"]');
 if(drawn!==isSubjective(session.draft))setTimeout(render);
},true);

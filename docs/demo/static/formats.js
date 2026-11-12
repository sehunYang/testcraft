// 교과별 세부 형식: 4종 유형은 그대로 두고 그 위에 평가원 꼴을 고른다. 목록은 /api/bootstrap 의 formats(app/question_formats.json).
function formatChoices(type){
 const subject=state.exam?.subject;
 return (state.boot?.formats||[]).filter(f=>f.subjects.includes(subject)&&(!type||f.types.includes(type)));
}
function formatInfo(id){return (state.boot?.formats||[]).find(f=>f.id===id)}
function formatHint(id){const f=formatInfo(id);return f?`자료: ${f.material} · 발문: ${f.question}`:'고르지 않으면 유형만 따릅니다. 고르면 AI가 이 평가원 꼴로 문항을 씁니다.'}
function formatFieldHtml(value,type,attr){
 const list=formatChoices(type);if(!list.length&&!value)return '';
 const missing=value&&!list.some(f=>f.id===value)?`<option value="${esc(value)}" selected>${esc(formatInfo(value)?.name||value)} (이 유형·과목에 없음)</option>`:'';
 return `<label class="full format-field" data-format-field>세부 형식 <span class="muted">선택 사항</span><select ${attr}="format"><option value="">고르지 않음</option>${missing}${list.map(f=>`<option value="${esc(f.id)}" ${f.id===value?'selected':''}>${esc(f.name)}</option>`).join('')}</select><small class="hint" data-format-hint>${esc(formatHint(value))}</small></label>`;
}

const formatBaseField=field;
field=function(key,label,opts){
 const html=formatBaseField(key,label,opts);
 if(key!=='type')return html;const c=current();return c?html+formatFieldHtml(c.format||'',c.type,'data-field'):html;
};
const formatBaseCoreFields=authoringCoreFields;
authoringCoreFields=function(draft){return formatBaseCoreFields(draft)+formatFieldHtml(draft.format||'',draft.type,'data-authoring-field')};

// 유형을 바꾸면 그 유형에 맞는 형식만 남긴다. 맞지 않는 형식은 비운다.
function formatRefresh(select){
 const draft=select.matches('[data-authoring-field]'),holder=select.closest('form,.fields,.panel-body')?.querySelector('[data-format-field]');
 const target=draft?state.authoringDraft?.draft:current();if(!target)return;
 if(target.format&&!formatChoices(target.type).some(f=>f.id===target.format)){
  target.format='';
  if(draft)authoringPersistLocal();
  else{const field=holder?.querySelector('select');if(field){field.value='';field.dispatchEvent(new Event('input',{bubbles:true}))}}
 }
 const html=formatFieldHtml(target.format||'',target.type,draft?'data-authoring-field':'data-field');
 if(holder)holder.outerHTML=html||'';else if(html)select.closest('label')?.insertAdjacentHTML('afterend',html);
}
window.addEventListener('change',e=>{
 const el=e.target;
 if(el.matches?.('[data-field="type"],[data-authoring-field="type"]'))setTimeout(()=>formatRefresh(el));
 if(el.matches?.('[data-field="format"],[data-authoring-field="format"]')){const hint=el.closest('[data-format-field]')?.querySelector('[data-format-hint]');if(hint)hint.textContent=formatHint(el.value)}
},true);

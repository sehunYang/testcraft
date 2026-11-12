'use strict';
function distributionNudge(n, total, bins) {
 if(total<bins*2)return 'neutral';
 const average=total/bins, gap=Math.max(1,average*.25);
 return n-average>=gap?'high':average-n>=gap?'low':'neutral';
}
renderStats=function(){
 const el=$('#liveStats');el.hidden=!state.exam;if(!state.exam)return;
 const cards=state.exam.cards,count=(key,v)=>cards.filter(c=>c[key]===v).length;
 const answer=c=>{const a=String(c.answer||'').trim();return a&&'①②③④⑤'.includes(a)?'①②③④⑤'.indexOf(a)+1:Number(a)};
 const chip=(label,n)=>`<span class="count-chip">${esc(label)} <b>${n}</b></span>`;
 const group=(label,values,counts,missing)=>{
  const total=counts.reduce((a,b)=>a+b,0);
  return `<div class="count-group"><strong>${label}</strong>${values.map((v,i)=>{
   const level=distributionNudge(counts[i],total,values.length),pct=total?Math.round(counts[i]/total*100):0;
   const hint=level==='high'?'많음 · 다음 문항에서는 다른 항목을 고려하세요.':level==='low'?'적음 · 다음 문항에서 이 항목을 고려하세요.':'비중 참고';
   const title=`${label} ${v}: ${counts[i]}개 (${pct}%). ${hint} 선택 완료 ${values.length*2}문항부터 균등 비중 대비 차이를 안내합니다. 출제 의도에 따라 달리 구성할 수 있습니다.`;
   return `<span class="count-chip nudge-${level}" tabindex="0" data-distribution="${label}" data-value="${esc(v)}" title="${esc(title)}" aria-label="${esc(title)}">${esc(v)} <b>${counts[i]}</b>${level!=='neutral'?`<span class="nudge-mark">${level==='high'?'↑ 많음':'↓ 적음'}</span>`:''}</span>`;
  }).join('')}${missing?chip('미입력',missing):''}</div>`;
 };
 const standards={};for(const c of cards)if(c.standard)standards[c.standard]=(standards[c.standard]||0)+1;
 el.innerHTML=`<div class="counts-top"><b>${esc(subjectLabel())} · 현재 <span id="totalCount">${cards.length}</span>문항</b><span>AI 요청 Yes <b id="aiYesCount">${count('ai_requested',true)}</b> · 총 ${Number(cards.reduce((s,c)=>s+(Number(c.points)||0),0).toFixed(2))}점</span></div><div class="counts-grid">${group('문항 유형',state.boot.types,state.boot.types.map(t=>count('type',t)),count('type',''))}${group('난이도',['상','중','하'],['상','중','하'].map(t=>count('difficulty',t)),count('difficulty',''))}${group('정답',[1,2,3,4,5],[1,2,3,4,5].map(n=>cards.filter(c=>answer(c)===n).length),cards.filter(c=>!answer(c)).length)}</div><div class="count-group standard-counts"><strong>사용 성취기준</strong><div>${Object.entries(standards).map(([code,n])=>`<span title="${esc(state.standards[code]?.name||code)}">${chip(code,n)}</span>`).join('')||'<span class="muted">아직 선택한 성취기준이 없습니다.</span>'}</div></div><div class="nudge-legend">주황 ↑ 상대적으로 많음 · 파랑 ↓ 상대적으로 적음 <span>균등 비중은 참고용이며, 출제 의도에 따라 조정하세요.</span></div>`;
 document.documentElement.style.setProperty('--stats-height',`${el.offsetHeight+16}px`);
};

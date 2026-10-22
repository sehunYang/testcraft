'use strict';
// Supplemental help stays outside the fields and never hides required authoring controls.
const teacherHelpSections=[
 ['문항카드에는 무엇을 입력하나요?','시험의 과목을 먼저 고른 뒤 해당 과목의 성취기준, 난이도, 문항 유형과 핵심 아이디어를 입력하세요. 입력한 문항 수와 현재 분포는 상단에서 계속 확인할 수 있습니다.'],
 ['AI로 여러 문항을 한 번에 만들려면?','생성이 필요한 문항의 AI 요청을 Yes로 바꾸고 “Yes 문항 일괄 생성”을 누르세요. 완료된 문항은 No로 바뀌며, 실패한 문항은 Yes로 남아 다시 실행할 수 있습니다.'],
 ['문항카드 승인은 언제 하나요?','각 문항의 본문·답지·해설을 검토하고 문항 검토를 완료하세요. 100점 배점과 전체 문항 구성을 확인한 뒤 문항카드 전체 승인을 진행합니다. 실제 그림 제작은 이 승인 이후에 가능합니다.'],
 ['그림과 글씨는 어떻게 편집하나요?','그림 유형과 제작 범위를 확인한 뒤 그림을 생성하세요. “그림을 편집 객체로 변환”을 누르면 선·도형의 크기와 끝점을 조절할 수 있습니다. 물리량·수식·한글은 별도 글씨 객체로 편집하며, 배경만 재생성할 때도 유지됩니다.'],
 ['그림 유형 strict · mixed · flexible의 차이는?','strict는 정확한 SVG 규칙만, flexible은 창작 허용 영역만 사용합니다. mixed는 두 영역에 서로 다른 요소를 지정합니다. 그림 안에 글씨를 생성하도록 지시하지 말고 이미지 글씨 프롬프트에 따로 적으세요.'],
 ['시험지와 답지는 어디에서 받나요?','자료 그림까지 최종 확정한 뒤 “검토·출력”에서 누락 내용을 점검하고 시험지·답지 파일을 생성하세요. 출력 기록에서 학생용·교사용 시험지, 정답과 해설, 문항카드 파일을 받을 수 있습니다.']
];
const teacherBaseRender=render;
const teacherBaseWelcome=welcome;
welcome=function(){
 const exams=state.boot?.exams||[];
 if(!exams.length)return teacherBaseWelcome();
 return `<section class="exam-dashboard"><div class="dashboard-heading"><div><h2>내 시험</h2><p>작성하던 시험을 선택해 출제를 이어가세요.</p></div><button id="startWelcome" class="primary">＋ 새 시험 만들기</button></div><div class="exam-project-grid">${exams.map(e=>`<button class="exam-project" data-open-exam="${esc(e.id)}"><span class="project-tag">출제 작업실</span><span class="project-title">${esc(e.title)}</span><span class="project-meta">${esc(e.updated.slice(0,10).replaceAll('-','.'))} 수정</span><span class="project-open">이어서 작성 <span aria-hidden="true">→</span></span></button>`).join('')}</div><div class="dashboard-guide"><b>문항카드부터 학교 양식 출력까지</b><p>문항카드 작성 · AI 일괄 생성 · 카드 승인 · 그림과 글씨 편집 · 시험지와 답지 출력</p></div></section>`;
};
function groupTeacherFields(){
 const body=$('.edit-layout>section.panel>.panel-body');if(!body)return;
 const grids=[...body.children].filter(el=>el.classList.contains('fields'));if(grids.length!==2)return;
 const make=(id,title,children)=>{const fieldset=document.createElement('fieldset');fieldset.className='authoring-group full';fieldset.id=id;const legend=document.createElement('legend');legend.textContent=title;fieldset.append(legend);const grid=document.createElement('div');grid.className='fields';grid.append(...children);fieldset.append(grid);return fieldset};
 const first=make('authoring-basics','출제 기준',[...grids[0].children]);grids[0].replaceWith(first);
 const nodes=[...grids[1].children],groups={body:[],answer:[],plan:[]};
 for(const node of nodes){const key=node.querySelector('[data-field]')?.dataset.field;if(node.querySelector('.image-plan-fields'))groups.plan.push(node);else if(['answer','concepts','explanation'].includes(key))groups.answer.push(node);else groups.body.push(node)}
 grids[1].replaceWith(make('authoring-question','문항 구성',groups.body),make('authoring-answer','정답 · 해설',groups.answer),make('authoring-image-plan','그림 · 글씨 제작 계획',groups.plan));
 const oldHeading=[...body.children].find(el=>el.tagName==='H3'&&el.textContent==='문항 구성');if(oldHeading)oldHeading.remove();
 const jumps=document.createElement('nav');jumps.className='authoring-jumps';jumps.setAttribute('aria-label','문항 입력 구역');jumps.innerHTML=[['basics','출제 기준'],['question','문항 구성'],['answer','정답·해설'],['image-plan','그림 계획']].map(([id,text])=>`<button class="small-btn" data-authoring-jump="authoring-${id}">${text}</button>`).join('');body.prepend(jumps);
}
render=function(){
 teacherBaseRender();
 groupTeacherFields();
 if(!state.exam){$('#examTitle').textContent='선생님의 출제 작업실';$('#subtitle').textContent='시험을 만들고, 검토하고, 학교 양식으로 출력하세요.';$('#steps').hidden=true}else $('#steps').hidden=false;
 document.body.dataset.studioStage=state.exam?String(state.stage):'welcome';
 document.querySelectorAll('[data-stage]').forEach(el=>{if(state.exam&&Number(el.dataset.stage)===state.stage)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')});
 document.querySelectorAll('.item-btn.active,.exam-list button.active').forEach(el=>el.setAttribute('aria-current','true'));
 $('#workspaceHome').classList.toggle('active',!state.exam);
 $('#workspaceHome').disabled=state.job?.status==='running';
};
document.querySelector('.sidebar').id='studioSidebar';
$('#sidebarToggle').onclick=()=>{const closed=document.body.classList.toggle('sidebar-collapsed');$('#sidebarToggle').setAttribute('aria-expanded',String(!closed));$('#sidebarToggle').setAttribute('aria-label',closed?'작업실 메뉴 펼치기':'작업실 메뉴 접기');renderStats()};
$('#workspaceHome').onclick=()=>action(async()=>{if(state.job?.status==='running')throw Error('생성 완료 후 다른 시험으로 이동하세요.');await save();state.exam=null;state.job=null;state.stage=0;state.card=0;$('#jobBanner').hidden=true;state.boot=await api('/api/bootstrap');renderSidebar();render()});
document.addEventListener('click',e=>{
 const project=e.target.closest('[data-open-exam]');if(project){action(()=>openExam(project.dataset.openExam));return}
 const jump=e.target.closest('[data-authoring-jump]');if(jump){const fieldset=document.getElementById(jump.dataset.authoringJump);fieldset.scrollIntoView({block:'start',behavior:'instant'});const first=fieldset.querySelector('input,select,textarea');first?.focus({preventScroll:true});return}
 if(!e.target.closest('#teacherHelpBtn'))return;
 const holder=$('#teacherHelpBody'),stage=state.exam?state.stage:null;
 const context=stage===null?'새 시험 만들기에서 시작합니다.':['문항카드에서 출제 범위와 문항 구성을 정합니다.','문항 작성에서 문두·발문·답지·해설을 검토합니다.','자료 그림에서 그림과 독립 글씨 객체를 편집합니다.','검토·출력에서 시험지와 답지를 만듭니다.'][stage];
 holder.innerHTML=`<p class="help-context">${context}</p>${teacherHelpSections.map(([q,a],i)=>`<details ${i===(stage===null?0:[0,1,3,5][stage])?'open':''}><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('')}`;
 $('#teacherHelpDialog').showModal();
});

document.fonts.ready.then(()=>{if(state.boot)renderStats()});

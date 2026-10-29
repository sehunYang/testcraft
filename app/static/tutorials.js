'use strict';
// Contextual video help never mutates the exam, clicks controls or grants approvals.
(()=>{
 const help={catalog:null,open:false,minimized:false,episode:null,chapter:null,manual:false,guide:null,lastFocus:null};
 const $t=s=>document.querySelector(s),make=(tag,props={})=>Object.assign(document.createElement(tag),props);
 const panel=make('aside',{id:'tutorialPanel',className:'tutorial-panel',hidden:true});
 panel.setAttribute('aria-label','따라 하는 도움말');
 panel.innerHTML='<header class="tutorial-head"><div><h2>따라 하는 도움말</h2><small id="tutorialLocation"></small></div><div><button type="button" data-tutorial="minimize" aria-label="도움말 접기">−</button><button type="button" data-tutorial="close" aria-label="도움말 닫기">×</button></div></header><div class="tutorial-scroll"><label for="tutorialEpisode" class="sr-only">튜토리얼 선택</label><select id="tutorialEpisode"></select><p id="tutorialContext" class="tutorial-context"></p><div class="tutorial-player"><video id="tutorialVideo" controls playsinline preload="none" aria-label="사용 방법 영상"></video></div><p id="tutorialMediaStatus" class="tutorial-status" role="status" hidden>영상을 불러올 수 없습니다. 아래 글 안내와 화면 안내를 이용하거나 전체 영상을 새 창에서 열어 주세요.</p><div class="tutorial-tools"><button type="button" class="primary" data-tutorial="guide">화면에서 따라 하기</button><button type="button" data-tutorial="follow">현재 화면 안내</button></div><ol id="tutorialChapters" class="tutorial-chapters"></ol><details class="tutorial-transcript"><summary>글로 읽기 · 오프라인 안내</summary><div id="tutorialTranscript"></div></details></div><footer class="tutorial-footer"><a id="tutorialExternal" target="_blank" rel="noopener">영상 새 창에서 보기 ↗</a><a href="https://shy.ai.kr/testcraft/#tutorials" target="_blank" rel="noopener">전체 사용 안내 ↗</a></footer>';
 document.body.append(panel);
 const minimized=make('button',{className:'tutorial-minimize',textContent:'▶ 도움말 이어보기',hidden:true});document.body.append(minimized);
 const ring=make('div',{className:'tutorial-ring',hidden:true});ring.setAttribute('aria-hidden','true');
 const guide=make('section',{className:'tutorial-guide',hidden:true});guide.setAttribute('aria-label','현재 화면 조작 안내');guide.setAttribute('role','region');document.body.append(ring,guide);
 const guides={
  welcome:[['#newExamAction, #newExam, #startWelcome','새 시험 만들기','시험 제목과 과목을 선택해 시작하세요.'],['#settingsBtn','AI 연결 확인','최초 계정 연결과 CLI 준비 상태를 확인합니다.']],
  design:[['#addCard, [data-ux-action="add-card"]','문항 추가','AI 초안 또는 직접 작성 중에서 고르세요.'],['#examStats, #stats, .distribution-summary, .stats','현재 분포','유형과 난이도 분포를 살펴보세요.'],['[data-ux-action="generate-questions"], [data-ux-action="connect"]','AI 초안 준비','필수 출제 기준을 채우고 생성할 문항을 선택하세요.']],
  author:[['[data-authoring-field="standard"]','출제 기준','성취기준·유형·난이도를 선택하세요.'],['[data-authoring-field="idea"]','핵심 아이디어','평가하려는 개념과 상황을 구체적으로 적으세요.'],['[data-authoring-request-kind]','자료 요청','그림·글상자·표를 함께 요청할 수 있습니다.'],['#authoringDraftForm button[type="submit"]','설계 저장','기준과 요청을 저장한 다음 일괄 생성을 실행합니다.']],
  review:[['[data-review-tab="question"]','문항 확인','문두·자료·발문을 미리보기와 함께 확인하세요.'],['[data-review-tab="answer"]','정답과 해설','선택지와 풀이, 검산을 확인하세요.'],['#openScorePanel','배점 조정','실제 문항을 보고 합계 100점으로 조절하세요.'],['[data-ux-action="review-current"], [data-ux-action="approve-exam"]','검토와 승인','문항별 검토를 완료한 뒤 전체 출제안을 승인하세요.']],
  figure:[['[data-field="image_mode"], .image-plan-readonly','그림 유형','strict는 고정 규칙만, flexible은 창작 영역만 사용합니다. mixed는 서로 다른 요소를 지정합니다.'],['[data-field="image_text_physics"], .planned-labels','독립 글씨 계획','그림에는 글씨를 그리지 않고 물리량·수식·한글을 별도로 계획하세요.'],['[data-ux-action="confirm-plan"], #confirmImagePlan, [data-ux-action="generate-image"]','계획 확인과 생성','전체 출제안 승인 후 그림의 계획을 확인하고 생성하세요.']],
  editor:[['[data-vector-action="expand"]','편집 공간','넓게 편집으로 캔버스를 확장할 수 있습니다.'],['#layerCanvas','그림과 글씨','객체를 선택해 움직이고 손잡이로 크기와 각도를 조절하세요.'],['#designerObjectToolbar','선택 객체 도구','선택 후 복제·삭제·겹침 순서를 위쪽 도구에서 바꿉니다.'],['#designerSnap, #vectorSnap','스냅','회전과 객체 정렬을 맞추는 스냅 설정을 확인하세요.'],['[data-ux-action="save-image-edit"], [data-ux-action="approve-image"]','완성본 확인','편집을 저장하고 최종 확인에서 그림을 확정하세요.']],
  export:[['[data-ux-action="first-output-issue"], [data-ux-action="create-export"]','출력 준비','남은 확인 항목을 해결한 뒤 시험지를 만드세요.'],['a[href*=".hwpx"]','한글 파일 받기','학생용·교사용·정답과 해설을 각각 받을 수 있습니다.'],['a[href*=".zip"]','전체 받기','문항카드와 검수 기록도 함께 보관하세요.']]
 };
 function context(){
  if(typeof state==='undefined'||!state.exam)return {stage:'welcome',episode:'01-start',chapter:'welcome',name:'시작하기'};
  if(state.authoringDraft?.mode)return {stage:'author',episode:state.authoringDraft.mode==='ai'?'02-design':'03-author',chapter:state.authoringDraft.mode==='ai'?'criteria':'manual',name:'문항 추가'};
  if(state.stage===0)return {stage:'design',episode:'02-design',chapter:'distribution',name:'설계'};
  if(state.stage===1){const tab=typeof uxState==='undefined'?'question':uxState.tab;return {stage:'review',episode:tab==='plan'?'05-figure':'04-review',chapter:tab==='answer'?'answer':tab==='plan'?'modes':'question',name:'검토 · '+({answer:'정답·해설',plan:'그림 계획'}[tab]||'문항')};}
  if(state.stage===2){let step=0;try{step=imageFlowState().step}catch{}return {stage:step>=2?'editor':'figure',episode:step>=2?'06-editor':'05-figure',chapter:['flow','generate','objects','final'][step],name:'자료 그림 · '+['제작 계획','그림 생성','그림·글씨 편집','최종 확인'][step]};}
  return {stage:'export',episode:'07-export',chapter:'readiness',name:'출력'};
 }
 function safeAsset(value){try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='github.com'&&u.pathname.startsWith('/sehunYang/testcraft/releases/download/media-v1/')&&!u.username&&!u.password?u.href:null}catch{return null}}
 function time(seconds){return Math.floor(seconds/60)+':'+String(Math.floor(seconds%60)).padStart(2,'0')}
 function seek(seconds){const v=$t('#tutorialVideo');if(v.readyState>=1)v.currentTime=seconds;else v.addEventListener('loadedmetadata',()=>{v.currentTime=seconds},{once:true});}
 function showEpisode(id,chapter){
  const ep=help.catalog?.episodes.find(e=>e.id===id);if(!ep)return;
  const video=$t('#tutorialVideo'),changed=help.episode!==id;help.episode=id;help.chapter=chapter||ep.chapters[0].id;
  $t('#tutorialEpisode').value=id;$t('#tutorialContext').textContent=ep.description||'공개용 예제 시험을 실제로 만드는 과정입니다.';
  if(changed){video.pause();video.replaceChildren();video.src=safeAsset(ep.video)||'';const track=make('track',{kind:'subtitles',label:'한국어',srclang:'ko',src:ep.captions,default:true});if(/^\/tutorials\/[a-z0-9-]+\.vtt$/.test(ep.captions))video.append(track);$t('#tutorialMediaStatus').hidden=true;$t('#tutorialExternal').href=safeAsset(ep.video)||'https://shy.ai.kr/testcraft/#tutorials';video.load();}
  const list=$t('#tutorialChapters');list.replaceChildren();const transcript=$t('#tutorialTranscript');transcript.replaceChildren();
  ep.chapters.forEach(c=>{const li=make('li'),b=make('button',{type:'button'});b.setAttribute('aria-current',String(c.id===help.chapter));b.append(make('time',{textContent:time(c.start)}),make('span',{textContent:c.title}));b.onclick=()=>{help.chapter=c.id;seek(c.start);list.querySelectorAll('button').forEach(x=>x.setAttribute('aria-current',String(x===b)))};li.append(b);list.append(li);transcript.append(make('b',{textContent:c.title}),make('p',{textContent:c.text}));});
  const selected=ep.chapters.find(c=>c.id===help.chapter);if(selected)seek(selected.start);
 }
 function follow(){help.manual=false;const c=context();$t('#tutorialLocation').textContent=c.name;showEpisode(c.episode,c.chapter)}
 function open(){help.lastFocus=document.activeElement;help.open=true;help.minimized=false;panel.hidden=false;minimized.hidden=true;document.body.classList.add('tutorial-open');if(help.catalog)follow();$t('#teacherHelpBtn')?.setAttribute('aria-expanded','true');$t('#tutorialEpisode').focus();}
 function stopGuide(){help.guide=null;ring.hidden=true;guide.hidden=true}
 function close(){help.open=false;panel.hidden=true;minimized.hidden=true;document.body.classList.remove('tutorial-open');$t('#tutorialVideo').pause();stopGuide();$t('#teacherHelpBtn')?.setAttribute('aria-expanded','false');help.lastFocus?.isConnected&&help.lastFocus.focus()}
 function visibleTarget(selector){return [...document.querySelectorAll(selector)].find(el=>el.getClientRects().length&&!el.closest('[hidden]'))}
 function drawGuide(scroll=false){
  const g=help.guide;if(!g)return;const c=context();if(c.stage!==g.stage){stopGuide();return}
  const steps=guides[g.stage]||[],step=steps[g.index];if(!step){stopGuide();return}
  const el=visibleTarget(step[0]);ring.hidden=!el;
  if(el){if(scroll)el.scrollIntoView({block:'center',behavior:'instant'});const r=el.getBoundingClientRect();Object.assign(ring.style,{left:r.left-5+'px',top:r.top-5+'px',width:r.width+10+'px',height:r.height+10+'px'});}
  guide.hidden=false;guide.replaceChildren(make('b',{textContent:step[1]}),make('p',{textContent:el?step[2]:'이 항목이 현재 화면에 없습니다.'}));
  if(!el)guide.querySelector('p').textContent='이 항목이 현재 화면에 없습니다. 먼저 앞 단계를 완료하거나 해당 구역을 열어 주세요. '+step[2];
  const footer=make('footer'),counter=make('small',{textContent:`${g.index+1} / ${steps.length}`}),end=make('button',{type:'button',textContent:'종료'}),next=make('button',{type:'button',textContent:g.index+1===steps.length?'마침':'다음',className:'primary'});end.onclick=stopGuide;next.onclick=()=>{g.index++;drawGuide(true)};footer.append(counter,end,next);guide.append(footer);
  const rect=el?.getBoundingClientRect(),width=Math.min(340,innerWidth-24);guide.style.width=width+'px';guide.style.left=Math.max(12,Math.min(innerWidth-width-12,rect?rect.left:16))+'px';guide.style.top=Math.max(12,Math.min(innerHeight-guide.offsetHeight-12,rect?rect.bottom+14:100))+'px';
 }
 window.addEventListener('click',event=>{if(event.target.closest('#teacherHelpBtn')){event.preventDefault();event.stopImmediatePropagation();if(help.minimized)minimized.click();else help.open?close():open()}},true);
 panel.addEventListener('click',e=>{const action=e.target.closest('[data-tutorial]')?.dataset.tutorial;if(action==='close')close();if(action==='minimize'){panel.hidden=true;minimized.hidden=false;help.minimized=true;help.minimizedContext=JSON.stringify(context());document.body.classList.remove('tutorial-open');$t('#tutorialVideo').pause();stopGuide()}if(action==='follow')follow();if(action==='guide'){const c=context();$t('#tutorialVideo').pause();help.guide={stage:c.stage,index:0};drawGuide(true)}});
 minimized.onclick=()=>{help.minimized=false;panel.hidden=false;minimized.hidden=true;document.body.classList.add('tutorial-open');if(!help.manual&&help.minimizedContext!==JSON.stringify(context()))follow()};
 $t('#tutorialEpisode').onchange=e=>{help.manual=true;stopGuide();showEpisode(e.target.value)};
 $t('#tutorialVideo').addEventListener('error',()=>{$t('#tutorialMediaStatus').hidden=false});
 window.addEventListener('keydown',e=>{if(e.key==='Escape'){if(help.guide){stopGuide();e.preventDefault()}else if(help.open&&!document.querySelector('dialog[open]')&&!document.body.classList.contains('vector-expanded'))close()}},true);
 window.addEventListener('resize',()=>drawGuide());window.addEventListener('scroll',()=>drawGuide(),true);
 const observer=new MutationObserver(()=>{if(!help.open)return;const c=context(),key=[c.stage,c.episode,c.chapter].join(':');if(help.key!==key){help.key=key;stopGuide();$t('#tutorialLocation').textContent=c.name;if(!help.manual&&!help.minimized)showEpisode(c.episode,c.chapter)}});
 observer.observe($t('main'),{childList:true,subtree:true});
 fetch('/tutorials-manifest.json').then(r=>{if(!r.ok)throw Error('catalog');return r.json()}).then(c=>{if(!Array.isArray(c.episodes)||!c.episodes.length)throw Error('catalog');help.catalog=c;const select=$t('#tutorialEpisode');c.episodes.forEach((e,i)=>select.append(make('option',{value:e.id,textContent:`${i+1}. ${e.title}`})));if(help.open)follow()}).catch(()=>{$t('#tutorialContext').textContent='도움말 목록을 불러오지 못했습니다. 전체 사용 안내를 새 창에서 열어 주세요.'});
 $t('#teacherHelpBtn')?.setAttribute('aria-controls','tutorialPanel');
 const comparison=$t('#uxModeSwitch');if(comparison)panel.querySelector('.tutorial-footer').append(comparison);
})();

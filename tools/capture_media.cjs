// Record actual UI actions against tools/serve_media_studio.py. No mocked results.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.runtime/media-production');
const info=JSON.parse(fs.readFileSync(path.join(out,'server.json'),'utf8'));
const script=JSON.parse(fs.readFileSync(path.join(__dirname,'media-script.json'),'utf8'));
if(!info.url.startsWith('http://127.0.0.1:')||!info.data_dir.includes('media-production'))throw Error('Recording requires isolated media server');
const from=Number(process.argv.find(x=>x.startsWith('--from='))?.split('=')[1]||0);
let page,context,epoch,epIndex=-1,scenes=[],raw;
if(from&&fs.existsSync(path.join(out,'capture.json'))){const prior=JSON.parse(fs.readFileSync(path.join(out,'capture.json'),'utf8'));scenes=prior.scenes.filter(s=>script.episodes.findIndex(e=>e.id===s.episode)<from);}
const errors=[];
async function click(selector){if(selector==='#newExam')selector='#newExamAction, #newExam, #startWelcome, [data-ux-action="new-exam"]';const el=page.locator(selector).filter({visible:true}).first();await el.scrollIntoViewIfNeeded();const box=await el.boundingBox();if(box){await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:18});await page.waitForTimeout(280)}await el.click();await page.waitForTimeout(450)}
async function fill(selector,value){const el=page.locator(selector).filter({visible:true}).first();await el.scrollIntoViewIfNeeded();await el.fill(value);await page.waitForTimeout(500)}
async function select(selector,value){const el=page.locator(selector).filter({visible:true}).first();await el.scrollIntoViewIfNeeded();await el.selectOption(value);await page.waitForTimeout(450)}
async function closeDialog(selector){if(await page.locator(selector+'[open]').count())await click(selector+' [data-close]')}
async function scene(id,action=async()=>{},hold=2.5){
 if(epIndex<from)return;
 const ep=script.episodes[epIndex],chapter=ep.chapters.find(c=>c.id===id);if(!chapter)throw Error(id);
 const start=(Date.now()-epoch)/1000;
 await page.evaluate(t=>{document.querySelector('#captureChapter').textContent=t},`${String(epIndex+1).padStart(2,'0')} · ${chapter.title}`);
 await action();await page.waitForTimeout(hold*1000);
 const end=(Date.now()-epoch)/1000;
 const still=path.join(out,'stills',ep.id+'-'+id+'.png');await page.screenshot({path:still});
 scenes.push({episode:ep.id,id,start,end,still:path.relative(out,still),raw});
 fs.writeFileSync(path.join(out,'capture.json'),JSON.stringify({raw,scenes,errors,source:'actual-browser-recording',ai:'real-codex-cli'},null,2));
 console.log(`${ep.id}/${id} ${Math.round(end-start)}s`);
}
async function waitJob(){if(epIndex<from)return;if(epIndex===6){await page.waitForSelector('a[href*=".hwpx"]',{timeout:240000});return}await page.waitForFunction(()=>state.job&&state.job.status!=='running',{},{timeout:1200000});const result=await page.evaluate(()=>({status:state.job.status,message:state.job.message}));if(result.status!=='completed')throw Error(JSON.stringify(result));await page.waitForTimeout(1000)}
async function addAI(idea,standard,material=false){
 await click('#addCard');await click('[data-authoring-choice="ai"]');
 await select('[data-authoring-field="standard"]',standard);
 await select('[data-authoring-field="type"]','단일 정답형');
 await select('[data-authoring-field="difficulty"]',material?'하':'중');
 await fill('[data-authoring-field="idea"]',idea);
 if(material){await page.locator('[data-authoring-request-kind="image"]').check();await select('[data-authoring-field="material_request_image_mode"]','strict');await fill('[data-authoring-field="materials_request"]','글씨 없는 수평면 위 상자와 오른쪽 힘 화살표 하나. 상자와 화살표는 서로 분리된 SVG 객체. 독립 물리량 글씨는 상자 위 m, 화살표 위 F 두 개만. 그림에 숫자나 글씨를 직접 그리지 않는다.');}
 await click('#authoringDraftForm button[type="submit"]');
}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  context=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:path.join(out,'raw'),size:{width:1600,height:1000}},reducedMotion:'reduce',bypassCSP:true});
  page=await context.newPage();raw=path.relative(out,await page.video().path());epoch=Date.now();page.setDefaultTimeout(20000);
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   addEventListener('DOMContentLoaded',()=>{
    const css=document.createElement('style');css.textContent='#captureCursor{position:fixed;width:18px;height:18px;border:3px solid #365eef;border-radius:50%;background:#365eef22;z-index:2147483646;pointer-events:none;transform:translate(-50%,-50%)}#captureChapter{position:fixed;bottom:14px;left:18px;background:#10234ee8;color:#fff;padding:9px 15px;border-radius:9px;font:600 14px sans-serif;z-index:2147483645;pointer-events:none}';document.head.append(css);
    const cursor=document.createElement('div');cursor.id='captureCursor';document.body.append(cursor);addEventListener('mousemove',e=>{cursor.style.left=e.clientX+'px';cursor.style.top=e.clientY+'px'});
    const label=document.createElement('div');label.id='captureChapter';label.textContent='TestCraft · 공개용 예제 실제 조작';document.body.append(label);
   });
  });
  await page.goto(info.url);await page.waitForFunction(()=>Boolean(state.boot)&&Object.keys(state.standards||{}).length>0);await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(700);
  if(from){const id=fs.readFileSync(path.join(out,'exam-id.txt'),'utf8');await page.evaluate(id=>openExam(id),id);if(from>=3)await click(`[data-stage="${from>=4?2:1}"]`);}
  epIndex=0;
  await scene('welcome');
  await scene('requirements',()=>click('#settingsBtn'));
  await scene('connection',async()=>{await page.locator('#cliStatus').scrollIntoViewIfNeeded();await page.waitForTimeout(1800)});
  await scene('new-exam',async()=>{await closeDialog('#settingsDialog');await click('#newExam');await fill('#createDialog [name="title"]','튜토리얼 예제 · 힘과 운동');await select('#createDialog [name="subject"]','12역학')});
  await scene('journey',()=>closeDialog('#createDialog'));
  epIndex=1;
  await scene('create',async()=>{await click('#newExam');await fill('#createDialog [name="title"]','튜토리얼 예제 · 힘과 운동');await select('#createDialog [name="subject"]','12역학');await click('#createDialog button[type="submit"]');await page.waitForFunction(()=>Boolean(state.exam));fs.writeFileSync(path.join(out,'exam-id.txt'),await page.evaluate(()=>state.exam.id))});
  const standard=await page.evaluate(()=>Object.keys(state.standards).find(k=>k.includes('12역학01-01'))||Object.keys(state.standards).find(k=>k.includes('12역학')));
  await scene('method',async()=>{await click('#addCard');await click('[data-authoring-choice="ai"]')});
  await scene('criteria',async()=>{await select('[data-authoring-field="standard"]',standard);await select('[data-authoring-field="type"]','단일 정답형');await select('[data-authoring-field="difficulty"]','하');await fill('[data-authoring-field="idea"]','마찰 없는 수평면 위 질량 m인 상자에 일정한 수평 힘 F가 작용한다. 가속도의 크기를 뉴턴 운동 법칙으로 판단하는 5지선다 문항. 복잡한 계산 없이 a=F/m을 고르게 한다. 수식과 물리량은 $...$로 감싼다. 답 ②. 선택지 ① F/(2m), ② F/m, ③ 2F/m, ④ m/F, ⑤ 2m/F. 독립 글씨는 m과 F만.')});
  await scene('materials',async()=>{await page.locator('[data-authoring-request-kind="image"]').check();await select('[data-authoring-field="material_request_image_mode"]','strict');await fill('[data-authoring-field="materials_request"]','수평면, 흰 상자, 오른쪽 힘 화살표를 분리된 SVG 객체로 만든다. 배경 글씨 금지. 상자 위 m과 화살표 위 F는 별도 물리량 글씨로만 지정. 검산식은 기호 F,m,a를 쓰지 말고 없음으로 한다.')});
  await scene('distribution',()=>click('#authoringDraftForm button[type="submit"]'));
  await scene('second',()=>addAI('같은 질량의 두 물체에 각각 F와 2F가 작용할 때 가속도를 비교한다. 자료 그림이나 표 없이 문장만으로 제시한다. 5지선다, 정답 ③. 보기의 단위를 통일하고 수식은 $...$로 작성한다.',standard));
  epIndex=2;
  await scene('pending');
  await scene('generate',()=>click('[data-ux-action="generate-questions"], [data-ux-action="retry-questions"]'),5);
  await waitJob();
  await scene('result',async()=>{await click('[data-ux-action="start-review"]');await page.waitForSelector('#previewSheet')});
  await scene('manual',async()=>{await click('[data-stage="0"]');await click('#addCard');await click('[data-authoring-choice="manual"]');await select('[data-authoring-field="standard"]',standard);await select('[data-authoring-field="type"]','단일 정답형');await select('[data-authoring-field="difficulty"]','하');await fill('[data-authoring-field="idea"]','힘이 작용하지 않는 물체의 운동 상태');await fill('[data-authoring-field="stem"]','마찰이 없는 수평면 위에서 물체가 일정한 속력으로 움직이고 있다.');await fill('[data-authoring-field="question"]','물체에 작용하는 알짜힘으로 옳은 것은?');await click('#authoringDraftForm button[type="submit"]')});
  await scene('revise',async()=>{await click('[data-review-tab="answer"]');await fill('[data-field="choices"]','① 운동 방향으로 작용한다.\n② 운동 반대 방향으로 작용한다.\n③ 위쪽으로 작용한다.\n④ 아래쪽으로 작용한다.\n⑤ 0이다.');await fill('[data-field="answer"]','5');await fill('[data-field="explanation"]','등속 직선 운동을 하므로 가속도는 0이다. 따라서 뉴턴 운동 법칙에 따라 물체에 작용하는 알짜힘은 0이다.');await click('#saveBtn')});
  fs.writeFileSync(path.join(out,'generated-checkpoint.json'),JSON.stringify(await page.evaluate(()=>state.exam),null,2));
  epIndex=3;
  await scene('question',async()=>{await click('[data-select="0"]');await click('[data-review-tab="question"]')});
  await scene('answer',()=>click('[data-review-tab="answer"]'));
  await scene('points',async()=>{await click('#openScorePanel');await click('#applyScore');await page.waitForTimeout(700)});
  await scene('plans',()=>click('[data-review-tab="plan"]'));
  await scene('approve',async()=>{
   // Each approval is the real UI command, subject to the same validation as users.
   for(let i=0;i<3;i++){
    const check=await page.evaluate(()=>({needed:current().calculation&&!current().checks?.length,no:current().no}));
    if(check.needed){await click('[data-review-tab="answer"]');await fill('#checksInput',check.no===1?'뉴턴 운동 법칙 | m*(F/m) | F':'가속도 비 | (2*F/m)/(F/m) | 2');await click('#verify');}
    await click('[data-ux-action="review-current"]');
    if(await page.locator('#approvalDiscrepancyDialog[open]').count())throw Error('Example needs calculation correction before approval');
    await page.waitForTimeout(500);
   }
   await page.waitForSelector('#confirmExamApproval');await click('#confirmExamApproval');
  });
  epIndex=4;
  await scene('flow',async()=>{await click('[data-select="0"]')});
  await scene('modes',async()=>{const el=page.locator('[data-field="image_mode"]');if(await el.count())await el.scrollIntoViewIfNeeded()});
  await scene('labels',async()=>{const el=page.locator('[data-field="image_text_physics"]');if(await el.count())await el.scrollIntoViewIfNeeded()});
  await scene('confirm',()=>click('[data-ux-action="confirm-plan"]'));
  await scene('generate',()=>click('[data-ux-action="generate-image"]'),5);
  await waitJob();
  await scene('ready',async()=>{await page.waitForFunction(()=>current()?.image&&current()?.labels_initialized);await page.waitForTimeout(1200)});
  fs.writeFileSync(path.join(out,'image-checkpoint.json'),JSON.stringify(await page.evaluate(()=>state.exam),null,2));
  epIndex=5;
  await scene('expand',async()=>{if(!await page.locator('#layerCanvas').count())await click('[data-image-step="2"]');if(await page.locator('[data-vector-action="convert"]').filter({visible:true}).count())await click('[data-vector-action="convert"]');await click('[data-vector-action="expand"]')});
  await scene('objects',async()=>{
   const row=page.locator('[data-design-select][data-kind="shape"]').filter({hasText:'box'}).first();await row.click();
   const id=await row.getAttribute('data-design-select'),box=await page.locator(`[data-vector="${id}"]`).boundingBox();
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:15});await page.mouse.down();await page.mouse.move(box.x+box.width/2+30,box.y+box.height/2,{steps:30});await page.mouse.up();
  });
  await scene('snap',async()=>{
   const controls=await page.locator('input').evaluateAll(nodes=>nodes.filter(n=>/rotation|angle/.test(n.outerHTML)).map(n=>n.outerHTML));
   fs.writeFileSync(path.join(out,'rotation-controls.json'),JSON.stringify(controls));
   const rotate=page.locator('[data-vprop="rotation"]');await rotate.fill('15');await rotate.dispatchEvent('change');await page.waitForTimeout(1400);await click('[data-design-action="undo"]');
   const snap=page.locator('[data-vector-action="snap"]');if(await snap.count())await click('[data-vector-action="snap"]');
  });
  await scene('text',async()=>{await click('[data-design-select][data-kind="label"]');const size=page.locator('[data-label-prop="size"]');await size.fill('34');await size.dispatchEvent('input');await page.waitForTimeout(900)});
  await scene('layers',async()=>{await click('[data-design-action="duplicate"]');await click('[data-design-action="undo"]')});
  await scene('regenerate',async()=>{await click('[data-vector-action="expand"]');await click('[data-image-step="1"]');await fill('#feedback','물리 상황은 유지하고 상자의 가로세로 비례만 조금 조절해 주세요. 기존 독립 글씨는 유지합니다.')});
  await scene('final',async()=>{await click('[data-image-step="2"]');await click('[data-ux-action="save-image-edit"]');await page.waitForTimeout(1500);await click('[data-ux-action="approve-image"]');if(await page.locator('#approvalDiscrepancyDialog[open]').count())throw Error('Figure mismatch needs correction')});
  epIndex=6;
  await scene('readiness',()=>click('[data-ux-action="go-export"]'));
  await scene('generate',()=>click('[data-hwpx-action="create"]'),4);
  await waitJob();
  await scene('documents',async()=>{await page.waitForSelector('a[href*=".hwpx"]')});
  await scene('download',async()=>{const [download]=await Promise.all([page.waitForEvent('download'),click('a[download][href$=".zip"]')]);await download.saveAs(path.join(out,'출제결과.zip'))});
  await scene('finish',async()=>{await page.mouse.move(1550,50,{steps:20})});
  fs.writeFileSync(path.join(out,'final-exam.json'),JSON.stringify(await page.evaluate(()=>state.exam),null,2));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'capture-error.png')}).catch(()=>{});console.error(await page.evaluate(()=>({exam:state.exam?.id,toast:document.querySelector('#toast')?.textContent})).catch(()=>({})))}throw error}finally{if(context)await context.close();await browser.close()}
 if(errors.length)throw Error(errors.join('\n'));
})().catch(e=>{console.error(e);process.exitCode=1});

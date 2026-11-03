const {chromium}=require('playwright');
const assert=require('node:assert/strict');
// Run against tests/serve_fixture.py on 8766; the example exam the episodes follow is seeded as a temporary exam.
(async()=>{
 const url=process.env.STUDIO_TEST_URL||'http://127.0.0.1:8766';
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForFunction(()=>Boolean(state.boot));
  await page.locator('#teacherHelpBtn').click();await page.locator('#tutorialEpisode option').nth(7).waitFor({state:'attached'});assert.equal(await page.locator('#tutorialEpisode option').count(),8);
  assert(await page.locator('#tutorialPanel').isVisible());assert.equal(await page.locator('#teacherHelpDialog').evaluate(e=>e.open),false,'help is nonmodal');
  assert.equal(await page.locator('#tutorialVideo').evaluate(v=>v.paused),true,'tutorial never autoplays');
  await page.locator('[data-tutorial="guide"]').click();assert(await page.locator('.tutorial-guide').isVisible());
  await page.keyboard.press('Escape');assert(await page.locator('#tutorialPanel').isVisible(),'Escape dismisses spotlight first');
  assert.equal(await page.locator('.tutorial-guide').isVisible(),false);
  await page.locator('[data-tutorial="minimize"]').click();assert(await page.locator('.tutorial-minimize').isVisible());
  await page.locator('.tutorial-minimize').click();assert(await page.locator('#tutorialPanel').isVisible());
  await page.locator('[data-tutorial="close"]').click();
  const id=await page.evaluate(async()=>{
   let e=await api('/api/create',{title:'튜토리얼 예제 · 충돌과 에너지',subject:'12역학'});
   Object.assign(e.cards[0],{standard:'[12역학01-01]',difficulty:'하',type:'최선답형',idea:'충돌 전후 운동량과 에너지를 비교한다.',stem:'두 수레가 충돌한다.',question:'옳은 것은?',choices:'① A\n② B\n③ C\n④ D\n⑤ E',answer:1,explanation:'A가 옳다.',points:'100',authoring_mode:'manual',ai_requested:false,data_kind:'image',material:'두 수레와 수평면',image_mode:'strict',image_locked:'floor: 수평선과 두 수레',image_text_none:true});
   e=await api('/api/save',{exam_id:e.id,revision:e.revision,cards:e.cards});return e.id;
  });
  {
   await page.evaluate(id=>openExam(id),id);const before=await page.evaluate(()=>JSON.stringify(state.exam));
   await page.locator('#teacherHelpBtn').click();assert.equal(await page.locator('#tutorialEpisode').inputValue(),'02-design');
   await page.locator('[data-stage="1"]').first().click();await page.waitForFunction(()=>document.querySelector('#tutorialEpisode').value==='04-review');
   await page.locator('.review-tabs [data-review-tab="answer"]').click();
   await page.waitForFunction(()=>document.querySelector('#tutorialChapters button[aria-current="true"]')?.textContent.includes('정답'));
   // Playing one chapter rings its control on this screen and stops where the next chapter begins.
   await page.locator('#tutorialChapters button[data-chapter="answer"]').click();
   await page.waitForFunction(()=>!document.querySelector('.tutorial-sync').hidden,null,{timeout:15000});
   assert.equal(await page.locator('.tutorial-sync span').textContent(),'정답·해설','ring names the uncovered control');
   await page.waitForFunction(()=>document.querySelector('#tutorialVideo').paused,null,{timeout:15000});
   const end=await page.evaluate(()=>document.querySelector('#tutorialVideo').currentTime);assert(end>15.9&&end<16.6,'chapter-only playback stops at its end: '+end);
   await page.locator('#tutorialChapters li',{hasText:'배점'}).locator('.tutorial-find').click();
   assert.equal(await page.locator('.tutorial-sync span').textContent(),'배점','find rings the control');
   await page.locator('#tutorialEpisode').selectOption('01-start');await page.locator('.review-tabs [data-review-tab="plan"]').click();
   assert.equal(await page.locator('#tutorialEpisode').inputValue(),'01-start','manual episode selection persists');
   await page.locator('[data-tutorial="follow"]').click();assert.equal(await page.locator('#tutorialEpisode').inputValue(),'05-figure');
   await page.locator('[data-tutorial="guide"]').click();await page.locator('[data-stage="3"]').first().click();
   await page.waitForFunction(()=>document.querySelector('#tutorialEpisode').value==='07-export');
   assert.equal(await page.locator('.tutorial-guide').isVisible(),false,'navigation stops spotlight');
   await page.locator('#tutorialVideo').dispatchEvent('error');assert(await page.locator('#tutorialMediaStatus').isVisible());
   await page.locator('.tutorial-transcript summary').click();assert(await page.locator('#tutorialTranscript').isVisible());
   assert.equal(await page.evaluate(()=>JSON.stringify(state.exam)),before,'help never changes exam data');
  }
  for(const width of [1440,1024,390,320]){await page.setViewportSize({width,height:900});const b=await page.locator('#tutorialPanel').boundingBox();assert(b&&b.x>=0&&b.x+b.width<=width+1,'help stays inside viewport');}
  await page.keyboard.press('Escape');assert.equal(await page.locator('#tutorialPanel').isVisible(),false);
  assert.deepEqual(errors,[]);console.log('Contextual tutorials, spotlight, state preservation, fallback and responsive checks passed.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

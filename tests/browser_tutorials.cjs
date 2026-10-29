const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const url=process.env.STUDIO_TEST_URL||JSON.parse(fs.readFileSync(path.join(__dirname,'../.runtime/media-production/server.json'),'utf8')).url;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForFunction(()=>Boolean(state.boot));
  await page.locator('#teacherHelpBtn').click();await page.locator('#tutorialEpisode option').nth(6).waitFor({state:'attached'});
  assert(await page.locator('#tutorialPanel').isVisible());assert.equal(await page.locator('#teacherHelpDialog').evaluate(e=>e.open),false,'help is nonmodal');
  assert.equal(await page.locator('#tutorialVideo').evaluate(v=>v.paused),true,'tutorial never autoplays');
  await page.locator('[data-tutorial="guide"]').click();assert(await page.locator('.tutorial-guide').isVisible());
  await page.keyboard.press('Escape');assert(await page.locator('#tutorialPanel').isVisible(),'Escape dismisses spotlight first');
  assert.equal(await page.locator('.tutorial-guide').isVisible(),false);
  await page.locator('[data-tutorial="minimize"]').click();assert(await page.locator('.tutorial-minimize').isVisible());
  await page.locator('.tutorial-minimize').click();assert(await page.locator('#tutorialPanel').isVisible());
  await page.locator('[data-tutorial="close"]').click();
  const id=await page.evaluate(()=>state.boot.exams.find(e=>e.title==='튜토리얼 예제 · 힘과 운동')?.id);
  if(id){
   await page.evaluate(id=>openExam(id),id);const before=await page.evaluate(()=>JSON.stringify(state.exam));
   await page.locator('#teacherHelpBtn').click();assert.equal(await page.locator('#tutorialEpisode').inputValue(),'02-design');
   await page.locator('[data-stage="1"]').first().click();await page.waitForFunction(()=>document.querySelector('#tutorialEpisode').value==='04-review');
   await page.locator('[data-review-tab="answer"]').click();
   await page.waitForFunction(()=>document.querySelector('#tutorialChapters button[aria-current="true"]')?.textContent.includes('정답'));
   await page.locator('#tutorialEpisode').selectOption('01-start');await page.locator('[data-review-tab="plan"]').click();
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

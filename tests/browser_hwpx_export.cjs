// Run against tests/serve_fixture.py. Network responses are mocked; no COM or teacher data.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 let requests=0,release;
 const pair=['시험지_학생용.hwpx','시험지_교사용.hwpx','정답과해설.hwpx'];
 const support=['문항카드.xlsx','검수기록.json'];
 const bundle=status=>({id:'1234567890abcdef',created:'2026-10-22T12:00:00',revision:1,
  content_digest:'fixture-content',conversion:{status,message:status==='ready'?'HWPX 준비 완료':'검증용 한글 변환 실패'},
  files:status==='ready'?[...pair,...support,'출제결과.zip']:support});
 try{
  await page.goto(process.env.STUDIO_TEST_URL||'http://127.0.0.1:8766');
  await page.waitForFunction(()=>Boolean(state.boot));
  await page.evaluate(async()=>{
   state.exam=await api('/api/create',{title:'HWPX 화면 검증',subject:state.boot.subjects[0].id});
   state.exam.validation={ready:true,errors:[],issues:[],warnings:[]};
   state.exam.content_digest='fixture-content';state.stage=3;state.boot.hwp_conversion_available=true;render();
  });
  await page.route('**/api/export',async route=>{
   requests++;await new Promise(resolve=>release=resolve);
   const exam=await page.evaluate(()=>structuredClone(state.exam));exam.exports=[bundle('failed')];
   await route.fulfill({json:exam});
  });
  await page.locator('[data-hwpx-action="create"]').click();
  await page.locator('#hwpxProgressDialog[open]').waitFor();
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('#hwpxProgressDialog .job-progress-spinner')).animationIterationCount==='infinite');
  await page.keyboard.press('Escape');
  assert(await page.locator('#hwpxProgressDialog').evaluate(el=>el.open));
  await page.waitForTimeout(100);assert.equal(requests,1);
  release();
  await page.locator('#hwpxProgressDialog').waitFor({state:'hidden'});
  assert.equal(await page.locator('a.download[href$=".hwpx"]').count(),0);
  assert.equal(await page.locator('a.download[href$=".hml"]').count(),0);
  assert.equal(await page.getByRole('link',{name:'전체 받기'}).count(),0);
  await page.route('**/api/recalculate',async route=>{
   requests++;const exam=await page.evaluate(()=>structuredClone(state.exam));exam.exports=[bundle('ready')];
   await route.fulfill({json:exam});
  });
  await page.locator('[data-recalc]').first().click();
  await page.locator('a.download[href$=".hwpx"]').first().waitFor();
  assert.equal(requests,2,'one handler per conversion');
  assert.equal(await page.locator('a.download[href$=".hwpx"]').count(),3);
  assert.equal(await page.locator('a.download[href$=".md"]').count(),0);
  assert.equal(await page.locator('#taskActionBar a').innerText(),'전체 받기');
  assert.equal(await page.locator('#hwpxProgressDialog').evaluate(el=>el.open),false);
  // A legacy bundle can be converted, but its old HML/ZIP cannot look like final HWPX output.
  await page.evaluate(()=>{
   state.exam.exports[0].files=['시험지_학생용.hml','시험지_교사용.hml','출제결과.zip','정답과해설.md'];
   delete state.exam.exports[0].conversion;state.boot.hwp_conversion_available=false;render();
  });
  assert.equal(await page.locator('a.download[href$=".hml"]').count(),0);
  assert.equal(await page.getByRole('link',{name:'전체 받기'}).count(),0);
  await page.route('**/api/bootstrap',async route=>{
   const boot=await page.evaluate(()=>structuredClone(state.boot));boot.hwp_conversion_available=true;
   await route.fulfill({json:boot});
  });
  await page.locator('[data-hwpx-action="check"]').first().click();
  await page.locator('[data-recalc]').first().waitFor();
  // An HTTP error must close the modal and allow a retry.
  await page.unroute('**/api/recalculate');
  await page.route('**/api/recalculate',route=>route.fulfill({status:500,json:{error:'검증용 연결 오류'}}));
  await page.locator('[data-recalc]').first().click();
  await page.waitForFunction(()=>!document.querySelector('#hwpxProgressDialog')?.open&&document.querySelector('#toast').textContent==='검증용 연결 오류');
  // The compatibility layout loads the same HWPX renderer without new-UI globals.
  await page.unroute('**/api/bootstrap');
  await page.goto((process.env.STUDIO_TEST_URL||'http://127.0.0.1:8766')+'/?ux=old');
  await page.waitForFunction(()=>Boolean(state.boot));
  await page.evaluate(async()=>{
   state.exam=await api('/api/create',{title:'기존 화면 HWPX 검증',subject:state.boot.subjects[0].id});
   state.exam.validation={ready:true,errors:[],issues:[],warnings:[]};state.stage=3;
   state.boot.hwp_conversion_available=true;render();
  });
  await page.locator('[data-hwpx-action="create"]').waitFor();
  assert.deepEqual(errors,[]);
  console.log('HWPX export browser checks passed: modal, failure, retry, pair/ZIP gating, legacy, compatibility');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});

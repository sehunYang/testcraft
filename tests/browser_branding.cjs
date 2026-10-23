const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const url=process.env.STUDIO_TEST_URL||'http://127.0.0.1:8766';
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:950}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForFunction(()=>Boolean(state.boot));
  assert.equal(await page.title(),'TestCraft · 교사를 위한 시험공방');
  assert.equal(await page.locator('meta[name="application-name"]').getAttribute('content'),'TestCraft');
  assert.equal(await page.locator('meta[property="og:site_name"]').getAttribute('content'),'TestCraft');
  const og=await page.locator('meta[property="og:image"]').getAttribute('content');
  assert.equal(new URL(og).origin,new URL(url).origin);
  for(const link of await page.locator('link[rel="icon"],link[rel="apple-touch-icon"]').evaluateAll(nodes=>nodes.map(n=>n.href))){
   const response=await page.request.get(link);assert.equal(response.status(),200,link);
  }
  for(const filename of ['favicon.ico','icons/icon-192.png','icons/icon-512.png','icons/testcraft.svg']){
   const response=await page.request.get(url+'/'+filename);assert.equal(response.status(),200);
   assert((await response.body()).equals(fs.readFileSync(path.join(__dirname,'../app/static',filename))));
  }
  const manifest=await(await page.request.get(url+'/site.webmanifest')).json();
  assert.equal(manifest.name,'TestCraft');assert.equal(manifest.short_name,'TestCraft');
  await page.locator('.topbar-brand').waitFor({state:'visible'});
  assert.equal(await page.locator('.topbar-brand').innerText(),'TestCraft');
  assert.equal(await page.locator('.topbar-brand img').evaluate(el=>el.complete&&el.naturalWidth>0),true);
  await page.locator('#sidebarToggle').click();
  await page.locator('.brand').waitFor({state:'visible'});
  assert.match(await page.locator('.brand').innerText(),/^TestCraft/);
  assert.equal(await page.locator('.brand-icon').evaluate(el=>el.complete&&el.naturalWidth>0),true);
  assert.equal((await page.locator('.brand small').innerText()).replace(/\s+/g,' '),'평가의 의도를 담아, 시험을 빚다.');
  assert.equal(await page.locator('.topbar-brand').isVisible(),false,'only one visible brand');
  await page.screenshot({path:path.join(__dirname,'../.runtime/testcraft-branded-ui.png')});
  await page.locator('#sidebarToggle').click();
  async function checkHeader(label){
   const boxes=await page.evaluate(()=>{
    const selectors=['#sidebarToggle','.topbar-brand','#crumbTitle','#teacherHelpBtn','#settingsBtn','#saveState','.exam-menu > summary'];
    return selectors.flatMap(selector=>{
     const el=document.querySelector(selector),rect=el?.getBoundingClientRect();
     if(!rect?.width||!rect.height||!el.checkVisibility())return [];
     return [{selector,x:rect.x,y:rect.y,right:rect.right,bottom:rect.bottom}];
    });
   });
   const viewport=page.viewportSize();
   for(const box of boxes){
    assert(box.x>=0&&box.right<=viewport.width+1,`${label}: ${box.selector} stays inside screen`);
    for(const other of boxes.filter(b=>b.selector!==box.selector)){
     assert(!(box.x<other.right-.5&&box.right>other.x+.5&&box.y<other.bottom-.5&&box.bottom>other.y+.5),`${label}: ${box.selector} overlaps ${other.selector}`);
    }
   }
   assert(await page.locator('.topbar-brand').isVisible(),label+': persistent brand');
  }
  for(const width of [1440,800,390,320]){
   await page.setViewportSize({width,height:950});await checkHeader('home '+width);
  }
  await page.evaluate(async()=>{
   state.exam=await api('/api/create',{title:'2026학년도 2학기 2차 지필평가 / 역학과 에너지 · 긴 시험 제목 가시성 확인',subject:state.boot.subjects[0].id});
   state.stage=0;render();
  });
  for(const width of [1440,1024,800,390,320]){
   await page.setViewportSize({width,height:950});await checkHeader('exam '+width);
   if(width===1440||width===390)await page.screenshot({path:path.join(__dirname,`../.runtime/testcraft-header-${width}.png`)});
  }
  await page.goto(url+'/?ux=old');await page.waitForFunction(()=>Boolean(state.boot));
  await page.setViewportSize({width:1440,height:950});
  if(await page.locator('.brand').isVisible())await page.locator('#sidebarToggle').click();
  await checkHeader('compatibility layout');
  await page.locator('#sidebarToggle').click();
  assert(await page.locator('.brand').isVisible());
  assert.equal(await page.locator('.topbar-brand').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log('TestCraft assets, Korean tagline, persistent branding, long-title/mobile header and compatibility layout: PASS');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});

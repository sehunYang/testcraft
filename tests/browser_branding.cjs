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
  await page.locator('#sidebarToggle').click();
  await page.locator('.brand').waitFor({state:'visible'});
  assert.match(await page.locator('.brand').innerText(),/^TestCraft/);
  assert.equal(await page.locator('.brand-icon').evaluate(el=>el.complete&&el.naturalWidth>0),true);
  await page.screenshot({path:path.join(__dirname,'../.runtime/testcraft-branded-ui.png')});
  assert.deepEqual(errors,[]);
  console.log('TestCraft title, metadata origin, approved icon assets, manifest and sidebar: PASS');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});

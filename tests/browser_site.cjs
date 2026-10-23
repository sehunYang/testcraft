const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const url=process.env.SITE_TEST_URL;if(!url)throw Error('Set SITE_TEST_URL to the guide preview.');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const snapshot=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/release.json'),'utf8'));
 const setup=snapshot.assets.find(asset=>asset.kind==='setup').url;
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);await page.waitForFunction(()=>document.querySelectorAll('[role="tab"]').length===3);
  await page.evaluate(()=>document.fonts.ready);
  assert(await page.evaluate(()=>document.fonts.check('18px "Studio Pretendard GOV"')),'app body font loaded');
  assert((await page.locator('body').evaluate(el=>getComputedStyle(el).fontFamily)).includes('Studio Pretendard GOV'));
  assert.match(await page.title(),/TestCraft/);
  for(const tab of await page.getByRole('tab').all()){
   await tab.click();const panel=page.locator('#'+await tab.getAttribute('aria-controls'));
   assert(await panel.isVisible());
   await panel.locator('img').evaluate(image=>image.decode());
  }
  await page.getByRole('tab').last().focus();await page.keyboard.press('Home');
  assert.equal(await page.getByRole('tab').first().getAttribute('aria-selected'),'true');
  await page.keyboard.press('ArrowRight');assert.equal(await page.getByRole('tab').nth(1).getAttribute('aria-selected'),'true');
  await page.getByRole('tab').first().click();
  for(const width of [1440,1024,768,390,320]){
   await page.setViewportSize({width,height:1000});
   assert(await page.locator('.hero-description').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=16));
   assert(await page.locator('.faq summary').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=18));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'horizontal overflow '+width);
   for(const cta of await page.locator('[data-download="setup"]').all()){
    assert.equal(await cta.getAttribute('href'),setup);
    const box=await cta.boundingBox();assert(box.width>0&&box.x>=0&&box.x+box.width<=width+1,'download visible '+width);
   }
   if(width===1440||width===390){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(__dirname,`../.runtime/testcraft-site-${width}.png`),fullPage:true})}
  }
  await page.locator('#faq details').first().locator('summary').click();assert(await page.locator('#faq details').first().getAttribute('open')!==null);
  const next=structuredClone(snapshot);next.version='v9.8.7';
  next.assets=next.assets.map(asset=>({...asset,name:asset.name.split(snapshot.version.slice(1)).join('9.8.7'),url:asset.url.split(snapshot.version.slice(1)).join('9.8.7')}));
  await page.route('**/release.json',route=>route.fulfill({json:next}));await page.reload();
  await page.waitForFunction(()=>document.querySelector('[data-release-version]').textContent==='v9.8.7');
  assert((await page.locator('[data-download="setup"]').first().getAttribute('href')).includes('/v9.8.7/'));
  await page.unroute('**/release.json');
  const bad=structuredClone(next);bad.assets[0].url='https://example.com/not-testcraft.exe';
  await page.route('**/release.json',route=>route.fulfill({json:bad}));await page.reload();
  await page.waitForFunction(()=>document.readyState==='complete');
  assert.equal(await page.locator('[data-download="setup"]').first().getAttribute('href'),setup);
  await page.unroute('**/release.json');await page.route('**/release.json',route=>route.fulfill({status:503,body:''}));
  await page.reload();assert.equal(await page.locator('[data-download="setup"]').first().getAttribute('href'),setup);
  const noScript=await browser.newContext({javaScriptEnabled:false});const plain=await noScript.newPage();await plain.goto(url);
  assert.equal(await plain.locator('[data-download="setup"]').first().getAttribute('href'),setup);await noScript.close();
  assert.deepEqual(errors,[]);
  console.log('Guide: responsive 320–1440px, keyboard tabs, FAQ, release updates, rejected external URL, offline metadata and no-JS downloads PASS');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});

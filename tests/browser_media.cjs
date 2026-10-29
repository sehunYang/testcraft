// Serve actual finished recordings in place of their public URLs for offline QA.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.join(root,'.runtime/media-production');
 const url=process.env.SITE_TEST_URL||JSON.parse(fs.readFileSync(path.join(out,'site-preview.json'),'utf8')).url;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://github.com/sehunYang/testcraft/releases/download/media-v1/**',route=>{
   const name=new URL(route.request().url()).pathname.split('/').pop();
   const bytes=fs.readFileSync(path.join(out,'finished',name)),range=route.request().headers().range?.match(/bytes=(\d+)-(\d*)/);
   const start=range?Number(range[1]):0,end=range&&range[2]?Math.min(Number(range[2]),bytes.length-1):bytes.length-1;
   return route.fulfill({status:range?206:200,body:bytes.subarray(start,end+1),contentType:'video/mp4',headers:{'Access-Control-Allow-Origin':'*','Accept-Ranges':'bytes','Content-Length':String(end-start+1),...(range?{'Content-Range':`bytes ${start}-${end}/${bytes.length}`}:{})}});
  });
  await page.goto(url);await page.waitForSelector('#siteTutorialList button');
  assert.equal(await page.locator('#siteTutorialList button').count(),7);
  assert(await page.locator('#heroLoop').evaluate(v=>v.paused&&v.muted),'reduced motion prevents background autoplay');
  await page.locator('#heroMotionToggle').click();await page.waitForFunction(()=>document.querySelector('#heroLoop').currentTime>0);
  await page.locator('#heroMotionToggle').click();assert(await page.locator('#heroLoop').evaluate(v=>v.paused));
  await page.locator('#siteTutorialVideo').scrollIntoViewIfNeeded();
  await page.locator('#siteTutorialVideo').evaluate(v=>v.play());
  await page.waitForFunction(()=>document.querySelector('#siteTutorialVideo').currentTime>0);
  await page.waitForFunction(()=>document.querySelector('#siteTutorialVideo').textTracks[0]?.cues?.length>0);
  await page.locator('#siteTutorialList button').nth(5).click();
  assert(await page.locator('#siteTutorialVideo').evaluate(v=>v.paused),'episode changes never autoplay');
  await page.locator('#siteTutorialChapters button').nth(2).click();
  try{await page.waitForFunction(()=>document.querySelector('#siteTutorialVideo').currentTime>40)}catch(error){console.error(await page.locator('#siteTutorialVideo').evaluate(v=>({time:v.currentTime,duration:v.duration,ready:v.readyState,error:v.error?.message,src:v.currentSrc,seekable:[...Array(v.seekable.length)].map((_,i)=>[v.seekable.start(i),v.seekable.end(i)])})));throw error}
  await page.locator('#watchShort').click();await page.waitForFunction(()=>document.querySelector('#shortDialog video').currentTime>0);
  assert(await page.locator('#siteTutorialVideo').evaluate(v=>v.paused),'short pauses tutorial');
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#shortDialog').open&&document.querySelector('#shortDialog video').paused);
  for(const width of [1440,1024,768,390,320]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow');}
  await page.setViewportSize({width:1440,height:1000});await page.locator('#tutorials').screenshot({path:path.join(out,'site-tutorials-qa.png')});
  assert.deepEqual(errors,[]);console.log('Actual videos, subtitles, seeking, short, motion preference and responsive media UI passed.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

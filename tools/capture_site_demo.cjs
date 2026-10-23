// Run against tests/serve_fixture.py only. Demo cards stay in browser memory.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const url=process.env.STUDIO_TEST_URL;
 if(!url||!/^http:\/\/127\.0\.0\.1:\d+$/.test(url)||url.endsWith(':8765'))throw Error('Set STUDIO_TEST_URL to the isolated fixture server.');
 const output=path.join(__dirname,'../docs/assets');fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);await page.waitForFunction(()=>Boolean(state.boot));
  await page.evaluate(()=>{
   const ideas=['일정한 힘을 받는 물체의 가속도와 질량의 관계','위치–시간 그래프에서 속도를 비교하는 문항','운동량 보존을 이용해 충돌 후 운동을 추론','마찰이 있는 빗면에서 역학적 에너지 변화를 분석','두 물체의 열평형 과정을 자료로 해석','상태 변화에서 열과 일, 내부 에너지의 관계'];
   state.exam={id:'dddddddddddddddd',title:'역학과 에너지 · 출제 예시',subject:'12역학',revision:1,updated:'2026-10-23T09:00:00',exports:[],card_approval:null,cards:ideas.map((idea,i)=>Object.assign(authoringBlankCard('demo00000000000'+i,i+1),{
    standard:['[12역학01-01]','[12역학01-01]','[12역학01-03]','[12역학01-04]','[12역학02-01]','[12역학02-03]'][i],
    difficulty:['하','중','중','상','하','상'][i],type:['단일 정답형','단일 정답형','합답형','합답형','불완전 문장형','짝짓기형'][i],idea,points:[12,16,16,22,12,22][i],answer:[2,4,1,3,5,2][i],
    stem:'그림과 같이 마찰이 없는 수평면에 놓인 질량이 $m$인 물체에 일정한 힘 $F$가 수평 방향으로 작용한다.',
    question:'물체의 가속도 크기로 옳은 것은?',choices:'① $F/(2m)$\n② $F/m$\n③ $2F/m$\n④ $m/F$\n⑤ $2m/F$',explanation:'뉴턴 운동 법칙에 따라 $F=ma$이므로 가속도의 크기는 $a=F/m$이다.',review_approved:i!==5,ai_requested:i===5,authoring_mode:'ai',data_kind:'none'
   }))};
   state.card=0;state.stage=0;state.dirty=false;render();
  });
  await page.screenshot({path:path.join(output,'studio-design.png')});
  await page.evaluate(()=>{state.stage=1;render()});
  await page.waitForFunction(()=>[...document.querySelectorAll('#previewSheet .preview-math-source')].every(node=>!previewNeedsMath(node.dataset.previewText)||node.dataset.previewMathReady==='true'));
  await page.waitForFunction(()=>[...document.querySelectorAll('#previewSheet img')].every(image=>image.complete&&image.naturalWidth>0));
  await page.screenshot({path:path.join(output,'studio-review.png')});
  await page.evaluate(()=>{
   const c=current();Object.assign(c,{materials:null,data_kind:'image',image_mode:'strict',image_plan_approval:{approved:true},labels_initialized:true,image:{file:'demo.png',approved:false},image_labels:[{id:'label00000000001',kind:'physics',text:'F',x:730,y:245,size:34,rotation:0},{id:'label00000000002',kind:'physics',text:'m',x:445,y:300,size:34,rotation:0}],image_scene:{defs:'',objects:[
    {id:'floor',name:'수평면',svg:'<g stroke="black" stroke-width="3"><path d="M100 420H900"/><path d="M110 420l-20 20M150 420l-20 20M190 420l-20 20M230 420l-20 20M270 420l-20 20M310 420l-20 20M350 420l-20 20M390 420l-20 20M430 420l-20 20M470 420l-20 20M510 420l-20 20M550 420l-20 20M590 420l-20 20M630 420l-20 20M670 420l-20 20M710 420l-20 20M750 420l-20 20M790 420l-20 20M830 420l-20 20M870 420l-20 20"/></g>'},
    {id:'block',name:'질량 m인 물체',svg:'<rect x="350" y="260" width="230" height="160" fill="white" stroke="black" stroke-width="3"/>'},
    {id:'force',name:'작용하는 힘',svg:'<path d="M580 340H825M805 325l20 15-20 15" fill="none" stroke="black" stroke-width="3"/>'}
   ].map(o=>({...o,matrix:[1,0,0,1,0,0],visible:true,locked:false}))}});
   state.exam.card_approval={approved:true};imageFlowStates.clear();state.stage=2;render();
  });
  await page.waitForFunction(()=>glyphPending.size===0);
  if(!await page.locator('#layerCanvas').count())await page.locator('[data-image-step="2"]').first().click();
  await page.locator('[data-design-select][data-kind="shape"]').nth(1).click();
  await page.locator('[data-vector-action="expand"]').click();
  await page.screenshot({path:path.join(output,'studio-designer.png')});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Captured three real UI screens using fictional, browser-only example cards.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});

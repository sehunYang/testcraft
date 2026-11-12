'use strict';
// Works on a project Pages URL as well as a local preview; no account or API call in the browser.
const tabs=[...document.querySelectorAll('[role="tab"]')];
function selectTab(tab,focus=false){
 for(const item of tabs){const selected=item===tab;item.setAttribute('aria-selected',String(selected));item.tabIndex=selected?0:-1;document.getElementById(item.getAttribute('aria-controls')).hidden=!selected}
 if(focus)tab.focus();
}
for(const tab of tabs){
 tab.addEventListener('click',()=>selectTab(tab));
 tab.addEventListener('keydown',event=>{
  const index=tabs.indexOf(tab),next={ArrowRight:(index+1)%tabs.length,ArrowLeft:(index+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1}[event.key];
  if(next!==undefined){event.preventDefault();selectTab(tabs[next],true)}
 });
}
function validRelease(release){
 if(!release||!/^v\d+\.\d+\.\d+$/.test(release.version)||!Array.isArray(release.assets)||release.assets.length!==3)return false;
 const prefix=`https://github.com/sehunYang/testcraft/releases/download/${release.version}/`;
 const names={setup:`TestCraft-${release.version.slice(1)}-windows-x64-setup.exe`,portable:`TestCraft-${release.version.slice(1)}-windows-x64-portable.zip`,checksums:'SHA256SUMS'};
 return Object.entries(names).every(([kind,name])=>release.assets.some(asset=>asset.kind===kind&&asset.name===name&&asset.url===prefix+name&&Number.isSafeInteger(asset.size)&&asset.size>0));
}
fetch(new URL('./release.json',document.baseURI),{cache:'no-cache'}).then(response=>{
 if(!response.ok)throw Error('Release snapshot unavailable');return response.json();
}).then(release=>{
 if(!validRelease(release))return;
 document.querySelectorAll('[data-release-version]').forEach(node=>node.textContent=release.version);
 for(const asset of release.assets){
  document.querySelectorAll(`[data-download="${asset.kind}"]`).forEach(node=>node.href=asset.url);
  document.querySelectorAll(`[data-release-size="${asset.kind}"]`).forEach(node=>node.textContent=(asset.size/1024/1024).toFixed(1)+' MB');
 }
 document.querySelectorAll('[data-release-notes]').forEach(node=>node.href=`https://github.com/sehunYang/testcraft/releases/tag/${release.version}`);
}).catch(()=>{/* Keep the verified, ordinary HTML download links usable without JavaScript or network metadata. */});
// 출제 흐름의 체험판: 누르면 실제 앱 화면(demo/)을 띄운다. 탭은 체험판의 단계도 함께 바꾼다.
(()=>{
 const box=document.querySelector('[data-demo]');if(!box)return;
 const screen=box.querySelector('.demo-screen'),poster=box.querySelector('.demo-poster'),start=box.querySelector('.demo-start');
 const posters=poster.dataset.posters.split(' ');let frame=null;
 const fit=()=>{if(frame)frame.style.transform=`scale(${screen.clientWidth/1440})`};
 start.addEventListener('click',()=>{
  if(matchMedia('(max-width:800px)').matches){window.open('./demo/index.html','_blank','noopener');return}   // 휴대폰은 화면이 좁아 새 창에서 연다
  frame=document.createElement('iframe');frame.src='./demo/index.html';frame.title='TestCraft 체험판';frame.allow='clipboard-write';
  screen.append(frame);fit();start.hidden=true;frame.addEventListener('load',()=>{poster.hidden=true});
  new ResizeObserver(fit).observe(screen);
 });
 box.querySelectorAll('[data-demo-stage]').forEach(tab=>tab.addEventListener('click',()=>{
  const n=+tab.dataset.demoStage;
  if(frame)frame.contentWindow?.postMessage({tcDemoStage:n},location.origin);else poster.src=posters[n];
 }));
})();

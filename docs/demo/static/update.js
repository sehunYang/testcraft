'use strict';
// 새 버전 알림과 한 번 클릭 업데이트. 앱을 켤 때와 하루 한 번 서버가 홈페이지의 release.json 을 확인한다.
(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const KEY='testcraft-update-later';
let st=null,timer=0;
const later=()=>{try{return localStorage.getItem(KEY)}catch{return null}};
function bar(){let el=document.querySelector('#updateBar');if(!el){el=document.createElement('div');el.id='updateBar';el.className='update-bar';el.setAttribute('role','status');el.hidden=true;document.body.prepend(el)}return el}
function draw(){const el=bar();
 if(!st?.available||(!st.stage&&!st.install_error&&later()===st.latest)){el.hidden=true;return}
 el.hidden=false;const mb=st.size?` · ${(st.size/1024/1024).toFixed(0)}MB`:'';
 if(st.stage==='downloading'){const pct=st.size?Math.round(st.received/st.size*100):0;el.innerHTML=`<b>${esc(st.latest)} 받는 중</b><progress max="100" value="${pct}"></progress><span>${pct}%</span><small>받은 뒤 파일을 검증하고 설치합니다. 계속 작업하셔도 됩니다.</small>`;return}
 if(st.stage==='installing'){el.innerHTML=`<b>${esc(st.latest)} 설치 중</b><small>설치가 끝나면 TestCraft가 새 창으로 다시 열립니다. 이 탭은 닫으셔도 됩니다. 작업 내용은 저장되어 있습니다.</small>`;return}
 el.innerHTML=`<b>새 버전 ${esc(st.latest)}이 나왔습니다</b><small>지금 ${esc(st.current)}${mb}</small>${st.install_error?`<small class="warn">${esc(st.install_error)}</small>`:''}
 <span class="update-actions"><a href="${esc(st.notes)}" target="_blank" rel="noopener">바뀐 점</a>${st.can_install?'<button type="button" class="primary" data-update-now>지금 업데이트</button>':`<a class="button" href="${esc(st.home)}" target="_blank" rel="noopener">홈페이지에서 받기</a>`}<button type="button" data-update-later>나중에</button></span>`}
async function load(){try{st=await (await fetch('/api/update/status')).json()}catch{return}
 draw();clearTimeout(timer);
 if(st.stage==='downloading')timer=setTimeout(load,1000);
 else if(st.stage!=='installing')timer=setTimeout(load,60*60*1000)}   // 켜 둔 채로 두어도 서버가 하루 한 번 다시 확인한다
window.addEventListener('click',async e=>{const t=e.target;
 if(t.closest('[data-update-later]')){try{localStorage.setItem(KEY,st.latest)}catch{}bar().hidden=true;return}
 if(t.closest('[data-update-now]')){t.closest('button').disabled=true;
  try{if(typeof save==='function')await save();st=await api('/api/update/install',{});draw();clearTimeout(timer);timer=setTimeout(load,1000)}
  catch(err){toast(err.message||String(err));t.closest('button').disabled=false}}
},true);
setTimeout(load,1500);
})();

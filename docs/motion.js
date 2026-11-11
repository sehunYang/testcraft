'use strict';
// 스크롤하면 섹션과 카드가 차례로 떠오른다. 기출 변형의 변형 방식은 차례로 켜진다. 동작 줄이기 설정에서는 쉰다.
(()=>{
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const targets=document.querySelectorAll('.section-heading,.idea-card,.idea-arrow,.variant-methods,.variant-card,.variant-changes,.variant-facts li,.process li,.studio-showcase,.figure-grid figure,.figure-more,.short-cards figure,.tutorial-intro,.tutorial-layout,.output-inner,.download-intro,.download-box,.install-steps li,.faq details,.faq>div:first-child');
 if('IntersectionObserver' in window&&!reduced.matches){
  document.documentElement.classList.add('js');
  const io=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){e.target.classList.add('in-view');io.unobserve(e.target)}},{threshold:.12,rootMargin:'0px 0px -40px 0px'});
  const order=new Map();
  targets.forEach(el=>{const n=order.get(el.parentElement)||0;order.set(el.parentElement,n+1);el.classList.add('reveal');el.style.transitionDelay=Math.min(n,5)*80+'ms';io.observe(el)});
 }
 const methods=[...document.querySelectorAll('.variant-methods span')];let k=0;
 if(methods.length)setInterval(()=>{if(reduced.matches||document.hidden)return;methods[k].classList.remove('on');k=(k+1)%methods.length;methods[k].classList.add('on')},2600);
})();
// 쇼츠 표지를 누르면 창이 열리고 소리와 함께 재생한다(자동 재생하지 않는다).
(()=>{
 const dialog=document.querySelector('#shortDialog');if(!dialog)return;const video=dialog.querySelector('video');
 document.querySelectorAll('[data-short]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelector('#heroLoop')?.pause();document.querySelector('#siteTutorialVideo')?.pause();
  video.src=button.dataset.short;video.muted=false;video.volume=1;dialog.showModal();video.play().catch(()=>{});
 }));
})();

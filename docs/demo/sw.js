// TestCraft 체험판: 앱 화면이 부르는 절대 경로(/app.js, /assets/..., /label-assets/...)를 체험판 폴더 안의 파일로 돌려준다.
// 서버 응답(/api/...)은 페이지의 demo-api.js가 맡는다. 체험판 밖의 홈페이지 요청은 건드리지 않는다.
'use strict';
const BASE = new URL('./', self.location).pathname;
const FONT = new URL('../assets/fonts/PretendardGOVVariable.woff2', self.location).pathname;
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith(BASE) || event.request.mode === 'navigate') return;
  const p = url.pathname, site = new URL('../', self.location).pathname;
  if (p.startsWith('/api/') || (site !== '/' && p.startsWith(site))) return;
  let target;
  if (p.startsWith('/assets/')) target = BASE + 'data/assets/' + p.split('/').pop();
  else if (p.startsWith('/label-assets/')) target = BASE + 'data/labels/' + p.split('/').pop();
  else if (p === '/fonts/pretendard-gov.woff2') target = FONT;
  else if (/^\/tutorials\/[0-9]{2}-[a-z-]+\.(jpg|vtt)$/.test(p)) target = site + 'media/' + p.split('/').pop();     // 도움말 영상: 홈페이지의 표지·자막
  else if (/^\/tutorials\/[0-9]{2}-[a-z-]+\.mp4$/.test(p)) { event.respondWith(Response.redirect('https://github.com/sehunYang/testcraft/releases/download/media-v1/' + p.split('/').pop(), 302)); return; }
  else if (/^\/[A-Za-z0-9_\-./]+\.(js|css|json|png|svg|ico|webmanifest|woff2)$/.test(p) && !p.includes('..')) target = BASE + 'static' + p;
  else return;
  event.respondWith(fetch(target + url.search, {credentials: 'same-origin'}));
});

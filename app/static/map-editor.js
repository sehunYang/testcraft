'use strict';
// 지도 자료 편집. SVG 규칙 칸의 "지도: {JSON}" 명세를 화면에서 고르고 끌어 옮긴다. 명세는 그 칸에 다시 써서 기존 저장·승인 흐름을 그대로 탄다.
const MAP_PREFIX='지도:',MAP_W=1000,MAP_H=640,MAP_MARGIN=6;
const mapViewNames={world:'세계',east_asia:'동아시아',korea:'한반도',south_korea:'남한',japan:'일본',china:'중국',southeast_asia:'동남아시아',south_asia:'남아시아',central_asia:'중앙아시아',silk_road:'실크로드',middle_east:'서아시아',mediterranean:'지중해',europe:'유럽',africa:'아프리카',north_america:'북아메리카',south_america:'남아메리카',oceania:'오세아니아',atlantic:'대서양',indian_ocean:'인도양',pacific:'태평양',globe:'지구 전체'};
const mapPeriods=[[2.6,'제4기'],[23,'네오기'],[66,'팔레오기'],[145,'백악기'],[201,'쥐라기'],[252,'트라이아스기'],[299,'페름기'],[359,'석탄기'],[419,'데본기'],[444,'실루리아기'],[485,'오르도비스기'],[539,'캄브리아기']];
const mapPaleoKinds={margin:'대륙붕까지 포함한 대륙',coast:'당시 해안선'};
const mapGroups={points:'점',blobs:'번지는 음영',shade:'나라·지역 음영',areas:'영역',routes:'경로',lines:'점선 위선·경선',callouts:'말풍선'};
const mapMovable={points:'at',blobs:'at',callouts:'at',routes:'path',areas:'points'};
const mapShadeUnits={countries:'나라',provinces:'시·도',districts:'시·군·구'};
const mapPatternNames={gray:'회색',dark:'진한 회색',hatch:'빗금',white:'흰색'};
const mapSideNames={right:'오른쪽',left:'왼쪽',up:'위',down:'아래'};
const mapEd={spec:null,source:'',preview:null,options:null,polities:{},selected:null,vertex:null,drag:null,timer:0,request:0,writing:false};

function mapIsSpec(text){return String(text||'').trim().startsWith(MAP_PREFIX)}
function mapParse(text){try{const spec=JSON.parse(String(text).trim().slice(MAP_PREFIX.length));return spec&&typeof spec==='object'&&!Array.isArray(spec)?spec:null}catch{return null}}
function mapSubjectGroup(){return state.boot?.subjects?.find(s=>s.id===state.exam?.subject)?.group||''}
function mapBox(spec){const view=spec?.view;return Array.isArray(view)?view:mapEd.options?.views?.[view]||null}
function mapRound(n){return Math.round(n*10)/10}
function mapGroupName(group){return group==='shade'&&mapEd.spec?.year!=null?'그해 나라 음영':mapGroups[group]}
function mapEra(spec){return spec?.ma!=null?'paleo':spec?.year!=null?'history':'modern'}
function mapAgeName(age){return age===0?'현재':`${age}Ma · ${(mapPeriods.find(([base])=>age<base)||mapPeriods.at(-1))[1]}`}
function mapYearName(year){return year<0?`기원전 ${-year}년`:`${year}년`}
// 그해에 있던 나라 목록은 연도마다 한 번만 받는다
function mapLoadPolities(year){
 if(year==null||mapEd.polities[year])return Promise.resolve(mapEd.polities[year]);
 return api('/api/map-polities?year='+encodeURIComponent(year)).then(r=>{mapEd.polities[year]=r.polities;return r.polities}).catch(()=>[]);
}
function mapPolityName(name){const found=(mapEd.polities[mapEd.spec?.year]||[]).find(p=>p.name===name||p.ko===name);return found?.ko||name}

function mapProject(lon,lat){const p=mapEd.preview?.projection;if(!p)return null;if(p.wraps&&lon<p.west)lon+=360;return [MAP_W/2+(lon-p.cx)*p.k*p.s,MAP_H/2-(lat-p.cy)*p.s]}
// 지금 위치(present)로 적은 표시는 미리보기가 준 판 회전으로 그때 위치에 보이고, 끌면 되돌려 지금 좌표로 저장한다.
function mapTurn(q,at,back){
 const [w,a,b,c]=q,s=back?-1:1,u=[a*s,b*s,c*s],la=at[1]*Math.PI/180,lo=at[0]*Math.PI/180,v=[Math.cos(la)*Math.cos(lo),Math.cos(la)*Math.sin(lo),Math.sin(la)];
 const cross=(p,q)=>[p[1]*q[2]-p[2]*q[1],p[2]*q[0]-p[0]*q[2],p[0]*q[1]-p[1]*q[0]],t=cross(u,v).map(x=>2*x),uc=cross(u,t);
 const r=v.map((x,i)=>x+w*t[i]+uc[i]);
 return [mapRound(Math.atan2(r[1],r[0])*180/Math.PI),mapRound(Math.asin(Math.max(-1,Math.min(1,r[2])))*180/Math.PI)];
}
function mapShown(group,index,item,vertex,at){const q=item.present&&mapEd.preview?.turns?.[`${group}:${index}`]?.[vertex];return q?mapTurn(q,at):at}
function mapStored(group,index,item,vertex,at){const q=item.present&&mapEd.preview?.turns?.[`${group}:${index}`]?.[vertex];return q?mapTurn(q,at,true):at}
function mapUnproject(x,y){const p=mapEd.preview.projection;x=Math.max(MAP_MARGIN,Math.min(MAP_W-MAP_MARGIN,x));y=Math.max(MAP_MARGIN,Math.min(MAP_H-MAP_MARGIN,y));let lon=p.cx+(x-MAP_W/2)/(p.k*p.s);if(lon>180)lon-=360;return [mapRound(lon),mapRound(p.cy-(y-MAP_H/2)/p.s)]}
function mapCenter(){const box=mapBox(mapEd.spec)||[-170,-58,180,78];let lon=(box[0]+box[2])/2;if(lon>180)lon-=360;return [mapRound(lon),mapRound((box[1]+box[3])/2)]}

function mapNextLabel(group){
 const used=new Set(Object.keys(mapGroups).flatMap(g=>(mapEd.spec[g]||[]).map(item=>item.label)));
 const pool=group==='points'?['A','B','C','D','E','F','G']:group==='routes'?[...'❶❷❸❹❺❻❼❽❾❿']:group==='lines'?['']:['(가)','(나)','(다)','(라)','(마)','(바)'];
 return pool.find(x=>!used.has(x))??pool[0];
}
function mapNewItem(group){
 const [lon,lat]=mapCenter(),box=mapBox(mapEd.spec)||[0,0,40,20],dx=mapRound((box[2]-box[0])/8),dy=mapRound((box[3]-box[1])/8),label=mapNextLabel(group);
 const korea=['korea','south_korea'].includes(mapEd.spec.view);
 return {points:{at:[lon,lat],label},blobs:{at:[lon,lat],radius:[dx,dy],label},shade:mapEd.spec.year!=null?{polities:[],label,pattern:'gray'}:korea?{provinces:[],label,pattern:'gray'}:{countries:[],label,pattern:'gray'},
  areas:{points:[[mapRound(lon-dx),mapRound(lat-dy)],[mapRound(lon+dx),mapRound(lat-dy)],[lon,mapRound(lat+dy)]],label,pattern:'gray'},
  routes:{path:[[mapRound(lon-dx),lat],[mapRound(lon+dx),lat]],label,dash:false,arrow:true},lines:{lat:0,label:'0°'},callouts:{at:[lon,lat],text:label+' 지역'}}[group];
}

// 명세를 SVG 규칙 칸에 다시 써서 기존 입력 처리(저장 표시, 승인 해제)를 그대로 쓴다.
function mapWrite(){
 const text=MAP_PREFIX+' '+JSON.stringify(mapEd.spec),field=document.querySelector('[data-field="image_locked"]');
 mapEd.source=text;if(!field)return;field.value=text;mapEd.writing=true;
 try{field.dispatchEvent(new Event('input',{bubbles:true}))}finally{mapEd.writing=false}
 mapSchedulePreview();
}
function mapSchedulePreview(delay=200){clearTimeout(mapEd.timer);mapEd.timer=setTimeout(mapLoadPreview,delay)}
async function mapLoadPreview(){
 const request=++mapEd.request,locked=MAP_PREFIX+' '+JSON.stringify(mapEd.spec);
 try{
  if(!mapEd.options)mapEd.options=await api('/api/map-options');
  const result=await api('/api/map-preview',{locked});
  if(request!==mapEd.request)return;mapEd.preview=result;
 }catch(error){if(request===mapEd.request)mapEd.preview={errors:[error.message]}}
 mapDraw();mapRenderErrors();
}

function mapEditorHtml(c,readonly){
 const spec=mapParse(c.image_locked);
 if(!spec)return `<section class="map-editor"><p class="map-errors" role="alert">지도 명세의 JSON을 읽을 수 없습니다. SVG 규칙 칸을 고치거나 새 지도로 시작하세요.</p>${readonly?'':'<button type="button" class="small-btn" data-map-action="reset">새 지도로 시작</button>'}</section>`;
 const notice=!readonly&&c.image_mode!=='strict'?'<p class="map-errors" role="alert">지도는 정확 도형(strict) 그림으로만 그립니다. <button type="button" class="small-btn" data-map-action="strict">strict로 바꾸기</button></p>':'';
 return `<section class="map-editor ${readonly?'is-readonly':''}" aria-label="지도 편집">
  <div class="map-editor-head"><b>지도 편집</b>${readonly?'':`<span class="hint">표시를 끌어 옮깁니다. 경로·영역을 고른 뒤 빈 곳을 누르면 꼭짓점이 늘어납니다.</span>`}</div>${notice}
  ${readonly?'':`<div class="map-view-row" data-map-view-row></div>`}
  <div class="map-editor-body"><div class="map-canvas-wrap"><svg class="map-canvas" viewBox="0 0 ${MAP_W} ${MAP_H}" role="application" aria-label="지도 미리보기. 표시를 끌어 위치를 옮깁니다." tabindex="0" data-map-canvas></svg></div>
  ${readonly?'':'<aside class="map-items" data-map-items></aside>'}</div>
  <p class="map-errors" role="status" data-map-errors></p>
  <p class="hint">해안선은 실제 자료입니다. 시대별 위치와 범위는 교사가 확인해 주세요. 글씨는 그림 생성 뒤 글씨 레이어에서 옮길 수 있습니다.</p></section>`;
}
function mapStartHtml(c){return `<div class="map-start"><button type="button" class="small-btn" data-map-action="start">실제 지도로 그리기</button><span class="hint">해안선을 실제 자료로 그리고 위치 표시만 고릅니다.</span></div>`}

function mapRenderViewRow(){
 const row=document.querySelector('[data-map-view-row]');if(!row||!mapEd.options)return;
 const spec=mapEd.spec,custom=Array.isArray(spec.view),box=mapBox(spec)||[0,0,0,0],era=mapEra(spec),years=mapEd.options.years||[-3400,2024];
 row.innerHTML=`<label>지도 범위<select data-map-prop="view">${Object.keys(mapEd.options.views).map(v=>`<option value="${v}" ${spec.view===v?'selected':''}>${esc(mapViewNames[v]||v)}</option>`).join('')}<option value="custom" ${custom?'selected':''}>경위도로 직접</option></select></label>
  ${custom?['서','남','동','북'].map((name,i)=>`<label class="map-num">${name}<input type="number" step="0.5" data-map-box="${i}" value="${box[i]}"></label>`).join(''):''}
  <label>시대<select data-map-prop="era">${[['modern','현대'],['history','역사 · 연도'],['paleo','지질시대']].map(([k,v])=>`<option value="${k}" ${era===k?'selected':''}>${v}</option>`).join('')}</select></label>
  ${era==='history'?`<label class="map-num">연도<input type="number" step="1" min="${years[0]}" max="${years[1]}" data-map-prop="year" value="${spec.year}" title="기원전은 음수로 적습니다"></label><span class="hint map-year-name">${esc(mapYearName(spec.year))}</span><label class="check-row"><input type="checkbox" data-map-flag="past_borders" ${spec.past_borders?'checked':''}>그해 국경 모두</label>`:''}
  ${era==='paleo'?`<label>시기<select data-map-prop="ma">${(mapEd.options.ages||[]).map(a=>`<option value="${a}" ${spec.ma===a?'selected':''}>${esc(mapAgeName(a))}</option>`).join('')}</select></label><label>바탕<select data-map-prop="paleo">${Object.entries(mapPaleoKinds).map(([k,v])=>`<option value="${k}" ${(spec.paleo||'margin')===k?'selected':''}>${v}</option>`).join('')}</select></label>`:''}
  ${era==='modern'?`<label class="check-row"><input type="checkbox" data-map-flag="borders" ${spec.borders?'checked':''}>현대 국경</label><label class="check-row"><input type="checkbox" data-map-flag="districts" ${spec.districts?'checked':''}>시·군·구 경계</label>`:''}
  ${era!=='paleo'?`<label class="check-row"><input type="checkbox" data-map-flag="rivers" ${spec.rivers?'checked':''}>큰 강</label>`:''}
  <label class="check-row"><input type="checkbox" data-map-flag="land" ${spec.land==='white'?'checked':''}>육지 흰색</label>
  ${era!=='paleo'?`<label class="map-num">축척 km<input type="number" min="0" step="10" data-map-prop="scale_km" value="${spec.scale_km||''}" placeholder="없음"></label>`:''}`;
}

function mapItemTitle(group,item){
 if(group==='shade'){const names=[...(item.countries||[]).map(code=>mapEd.options?.countries?.[code]||code),...(item.provinces||[]),...(item.districts||[]),...(item.polities||[]).map(mapPolityName)];return names.join(', ')||'칠할 곳 없음'}
 if(group==='callouts')return String(item.text||'').split('\n')[0];
 if(group==='lines')return 'lat' in item?`위도 ${item.lat}°`:`경도 ${item.lon}°`;
 const at=item.at||item.path?.[0]||item.points?.[0];return at?`${at[0]}, ${at[1]}`:'';
}
function mapRenderItems(){
 const holder=document.querySelector('[data-map-items]');if(!holder)return;
 const spec=mapEd.spec,sel=mapEd.selected,item=sel&&spec[sel.group]?.[sel.index];
 const list=Object.keys(mapGroups).flatMap(group=>(spec[group]||[]).map((x,index)=>`<button type="button" class="small-btn ${sel?.group===group&&sel.index===index?'secondary':''}" data-map-select="${group}:${index}"><b>${esc(x.label||(group==='callouts'?'말풍선':mapGroupName(group)))}</b><small>${esc(mapGroupName(group))} · ${esc(mapItemTitle(group,x))}</small></button>`)).join('');
 holder.innerHTML=`<div class="map-add"><label>표시 추가<select data-map-add><option value="">고르기</option>${Object.entries(mapGroups).filter(([g])=>!(g==='shade'&&mapEra(spec)==='paleo')).map(([g])=>`<option value="${g}">${mapGroupName(g)}</option>`).join('')}</select></label></div>
  <div class="map-item-list">${list||'<p class="hint">표시가 없습니다. 위에서 추가하세요.</p>'}</div>${item?mapItemProps(sel.group,item):''}`;
}
function mapItemProps(group,item){
 const label=`<label>표시 글씨<input data-map-item="label" value="${esc(item.label||'')}" placeholder="A, (가), ❶"></label>`;
 const pattern=`<label>칠하기<select data-map-item="pattern">${Object.entries(mapPatternNames).map(([k,v])=>`<option value="${k}" ${(item.pattern||'gray')===k?'selected':''}>${v}</option>`).join('')}</select></label>`;
 const lonlat=(at,key)=>`<label class="map-num">경도<input type="number" step="0.1" data-map-item="${key}.0" value="${at[0]}"></label><label class="map-num">위도<input type="number" step="0.1" data-map-item="${key}.1" value="${at[1]}"></label>`;
 let body='';
 if(group==='points')body=`${label}${lonlat(item.at,'at')}<label>글씨 방향<select data-map-item="side">${Object.entries(mapSideNames).map(([k,v])=>`<option value="${k}" ${(item.side||'right')===k?'selected':''}>${v}</option>`).join('')}</select></label><label class="check-row"><input type="checkbox" data-map-item="open" ${item.open?'checked':''}>빈 원</label>`;
 if(group==='blobs'){const r=item.radius||[5,3];body=`${label}${lonlat(item.at,'at')}<label class="map-num">경도 폭<input type="number" min="0.1" step="0.5" data-map-item="radius.0" value="${r[0]}"></label><label class="map-num">위도 폭<input type="number" min="0.1" step="0.5" data-map-item="radius.1" value="${r[1]}"></label>`}
 if(group==='shade'&&'polities' in item){
  const list=mapEd.polities[mapEd.spec.year],chosen=item.polities;
  const choices=(list||[]).filter(p=>!chosen.includes(p.name)).map(p=>[p.name,p.ko?`${p.ko} · ${p.name}`:p.name]);
  body=`${label}${pattern}<div class="map-chips">${chosen.map(name=>`<button type="button" class="small-btn" data-map-remove-place="${esc(name)}" aria-label="${esc(mapPolityName(name))} 빼기">${esc(mapPolityName(name))} ×</button>`).join('')||'<span class="hint">칠할 나라를 고르세요.</span>'}</div><label>${esc(mapYearName(mapEd.spec.year))}의 나라 더하기<select data-map-add-place="polities"><option value="">${list?'고르기':'불러오는 중…'}</option>${choices.map(([k,v])=>`<option value="${esc(k)}">${esc(v)}</option>`).join('')}</select></label><p class="hint">괄호로 싼 이름은 속한 나라를 모두 합친 범위입니다. 과거 영역은 하나의 견해이니 교과서와 대조해 주세요.</p>`;
 }
 else if(group==='shade'){
  const key=Object.keys(mapShadeUnits).find(k=>item[k]?.length)||Object.keys(mapShadeUnits).find(k=>k in item)||'countries',chosen=item[key]||[],countries=key==='countries';
  const choices=countries?Object.entries(mapEd.options?.countries||{}).sort((a,b)=>a[1].localeCompare(b[1],'ko')):(mapEd.options?.[key]||[]).map(n=>[n,n]);
  const unit=`<label>칠할 단위<select data-map-item="unit">${Object.entries(mapShadeUnits).map(([k,v])=>`<option value="${k}" ${key===k?'selected':''}>${v}</option>`).join('')}</select></label>`;
  body=`${label}${pattern}${unit}<div class="map-chips">${chosen.map(code=>`<button type="button" class="small-btn" data-map-remove-place="${esc(code)}" aria-label="${esc(code)} 빼기">${esc(countries?mapEd.options?.countries?.[code]||code:code)} ×</button>`).join('')||'<span class="hint">칠할 곳을 고르세요.</span>'}</div><label>${mapShadeUnits[key]} 더하기<select data-map-add-place="${key}"><option value="">고르기</option>${choices.filter(([k])=>!chosen.includes(k)).map(([k,v])=>`<option value="${esc(k)}">${esc(v)}</option>`).join('')}</select></label>${key==='districts'?'<p class="hint">시·군·구를 칠하면 남한은 통계청 경계로 그립니다.</p>':''}`;
 }
 if(group==='areas')body=`${label}${pattern}<p class="hint">꼭짓점 ${item.points.length}개 · 빈 곳을 누르면 늘어납니다.</p>`;
 if(group==='routes')body=`${label}<label class="check-row"><input type="checkbox" data-map-item="dash" ${item.dash?'checked':''}>점선</label><label class="check-row"><input type="checkbox" data-map-item="arrow" ${item.arrow!==false?'checked':''}>화살표</label><p class="hint">꼭짓점 ${item.path.length}개 · 빈 곳을 누르면 끝에 이어집니다.</p>`;
 if(group==='callouts'){const off=item.offset||['',''];body=`<label class="map-wide">말풍선 글<textarea rows="2" data-map-item="text">${esc(item.text||'')}</textarea></label>${lonlat(item.at,'at')}<label class="map-num">상자 가로<input type="number" step="10" data-map-item="offset.0" value="${off[0]}" placeholder="자동"></label><label class="map-num">상자 세로<input type="number" step="10" data-map-item="offset.1" value="${off[1]}" placeholder="자동"></label><p class="hint">꼬리가 가리킬 위치를 끌어 옮깁니다. 상자 위치는 가리킬 곳에서 떨어진 화면 거리입니다.</p>`}
 if(mapMovable[group]&&mapEra(mapEd.spec)==='paleo')body+=`<label class="check-row"><input type="checkbox" data-map-item="present" ${item.present?'checked':''}>지금 위치로 적기</label>${item.present?'<p class="hint">경위도는 지금의 위치입니다. 앱이 판 회전 모형으로 그 시기의 위치를 계산해 그립니다.</p>':''}`;
 if(group==='lines'){const lat='lat' in item;body=`${label}<label>방향<select data-map-item="axis"><option value="lat" ${lat?'selected':''}>위선</option><option value="lon" ${lat?'':'selected'}>경선</option></select></label><label class="map-num">${lat?'위도':'경도'}<input type="number" step="0.5" data-map-item="${lat?'lat':'lon'}" value="${lat?item.lat:item.lon}"></label>`}
 const vertex=['routes','areas'].includes(group)&&mapEd.vertex!=null?`<button type="button" class="small-btn" data-map-action="remove-vertex">고른 꼭짓점 삭제</button>`:'';
 return `<div class="map-item-props"><h4>${esc(mapGroupName(group))}</h4><div class="map-prop-grid">${body}</div><div class="buttons-wrap">${vertex}<button type="button" class="small-btn danger" data-map-action="remove">표시 삭제</button></div></div>`;
}
function mapRenderErrors(){const box=document.querySelector('[data-map-errors]');if(box)box.textContent=(mapEd.preview?.errors||[]).join(' / ')}

function mapHandles(){
 const out=[],sel=mapEd.selected;
 for(const group of Object.keys(mapMovable))(mapEd.spec[group]||[]).forEach((item,index)=>{
  const active=sel?.group===group&&sel.index===index,coords=group==='routes'?item.path:group==='areas'?item.points:[item.at];
  (coords||[]).forEach((at,vertex)=>{const shown=Array.isArray(at)&&mapShown(group,index,item,vertex,at),p=shown&&mapProject(shown[0],shown[1]);if(!p)return;const x=Math.max(MAP_MARGIN,Math.min(MAP_W-MAP_MARGIN,p[0])),y=Math.max(MAP_MARGIN,Math.min(MAP_H-MAP_MARGIN,p[1])),hot=active&&(coords.length===1||mapEd.vertex===vertex);
   out.push(`<circle class="map-handle ${active?'is-active':''} ${hot?'is-hot':''}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${active?13:10}" data-map-handle="${group}:${index}:${vertex}"/>`)});
 });
 return out.join('');
}
function mapDraw(){
 const canvas=document.querySelector('[data-map-canvas]');if(!canvas)return;const p=mapEd.preview;
 if(!p?.svg){canvas.innerHTML=`<rect width="${MAP_W}" height="${MAP_H}" fill="#f6f7f9"/><text x="500" y="320" text-anchor="middle" fill="#616873" font-size="24">${p?'지도를 그릴 수 없습니다. 아래 오류를 확인하세요.':'지도를 불러오는 중…'}</text>`;return}
 const labels=(p.labels||[]).map(o=>`<text x="${o.x}" y="${(o.y+o.size*0.85).toFixed(1)}" font-size="${o.size}" class="map-label">${esc(o.text)}</text>`).join('');
 canvas.innerHTML=`<image href="data:image/svg+xml;charset=utf-8,${encodeURIComponent(p.svg)}" width="${MAP_W}" height="${MAP_H}"/>${labels}${canvas.closest('.is-readonly')?'':mapHandles()}`;
}

function mapInit(section){
 section.dataset.mapReady='1';
 const text=String(current()?.image_locked||'');
 if(text!==mapEd.source){mapEd.spec=mapParse(text);mapEd.source=text;mapEd.selected=null;mapEd.vertex=null;mapEd.preview=null}
 if(!mapEd.spec)return;
 mapDraw();(mapEd.options?Promise.resolve():api('/api/map-options').then(o=>mapEd.options=o)).then(()=>mapLoadPolities(mapEd.spec.year)).then(()=>{mapRenderViewRow();mapRenderItems()}).catch(()=>{});
 mapLoadPreview();
 const canvas=section.querySelector('[data-map-canvas]');if(section.classList.contains('is-readonly'))return;
 const point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(canvas.getScreenCTM().inverse());
 canvas.addEventListener('pointerdown',e=>{
  if(!mapEd.preview?.projection||state.job?.status==='running')return;
  const handle=e.target.closest('[data-map-handle]');
  if(handle){const [group,index,vertex]=handle.dataset.mapHandle.split(':');mapEd.selected={group,index:Number(index)};mapEd.vertex=Number(vertex);mapEd.drag={id:e.pointerId,moved:false};canvas.setPointerCapture(e.pointerId);canvas.focus();e.preventDefault();mapDraw();mapRenderItems();return}
  const sel=mapEd.selected,item=sel&&mapEd.spec[sel.group]?.[sel.index];
  if(item&&['routes','areas'].includes(sel.group)){const list=sel.group==='routes'?item.path:item.points;const p=point(e);list.push(mapStored(sel.group,sel.index,item,list.length-1,mapUnproject(p.x,p.y)));mapEd.vertex=list.length-1;mapDraw();mapRenderItems();mapWrite();return}
  mapEd.selected=null;mapEd.vertex=null;mapDraw();mapRenderItems();
 });
 canvas.addEventListener('pointermove',e=>{
  const drag=mapEd.drag;if(!drag||e.pointerId!==drag.id)return;const sel=mapEd.selected,item=mapEd.spec[sel.group][sel.index],p=point(e),at=mapStored(sel.group,sel.index,item,mapEd.vertex,mapUnproject(p.x,p.y));
  if(sel.group==='routes')item.path[mapEd.vertex]=at;else if(sel.group==='areas')item.points[mapEd.vertex]=at;else item.at=at;
  drag.moved=true;mapDraw();
 });
 const end=e=>{const drag=mapEd.drag;if(!drag||e.pointerId!==drag.id)return;mapEd.drag=null;if(drag.moved){mapRenderItems();mapWrite()}};
 canvas.addEventListener('pointerup',end);canvas.addEventListener('pointercancel',end);
 canvas.addEventListener('keydown',e=>{
  const sel=mapEd.selected,item=sel&&mapEd.spec[sel.group]?.[sel.index],deltas={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};
  if(!item||!deltas[e.key]||!mapMovable[sel.group])return;e.preventDefault();
  const step=e.shiftKey?1:0.1,[dx,dy]=deltas[e.key],list=sel.group==='routes'?item.path:sel.group==='areas'?item.points:[item.at],at=list[mapEd.vertex??0]||list[0];
  at[0]=mapRound(at[0]+dx*step);at[1]=mapRound(at[1]+dy*step);mapDraw();mapRenderItems();mapWrite();
 });
}

// 시대를 바꾸면 그 시대에 쓸 수 없는 값만 뺀다. 점·영역·경로 표시는 그대로 둔다.
function mapSetEra(era){
 const spec=mapEd.spec;
 for(const key of ['year','past_borders','ma','paleo'])delete spec[key];
 if(era!=='modern')delete spec.districts;
 if(era!=='paleo')for(const group of Object.keys(mapMovable))for(const item of spec[group]||[])delete item.present;
 if(era==='history'){delete spec.borders;spec.year=1000}
 if(era==='paleo'){for(const key of ['borders','rivers','scale_km'])delete spec[key];spec.ma=250;spec.view='globe'}
 if(spec.shade){spec.shade=spec.shade.filter(item=>era==='history'?item.polities:era==='modern'&&!item.polities);if(!spec.shade.length)delete spec.shade}
 mapEd.selected=null;mapEd.vertex=null;
}
function mapSetPath(item,path,value){const keys=path.split('.');let target=item;for(const key of keys.slice(0,-1))target=target[key]??=[];target[keys.at(-1)]=value}
function mapStart(){
 const mode=document.querySelector('[data-field="image_mode"]');
 if(mode&&mode.value!=='strict'){mode.value='strict';mode.dispatchEvent(new Event('input',{bubbles:true}))}
 const field=document.querySelector('[data-field="image_locked"]');
 if(field){field.value=MAP_PREFIX+' '+JSON.stringify({view:'world',points:[]});field.dispatchEvent(new Event('input',{bubbles:true}))}
 render();
}

document.addEventListener('input',e=>{
 if(e.target.matches('[data-field="image_locked"]')&&!mapEd.writing){const section=document.querySelector('.map-editor');if(mapIsSpec(e.target.value)!==!!section){requestAnimationFrame(()=>render());return}if(section){const spec=mapParse(e.target.value);mapEd.source=e.target.value;if(spec){mapEd.spec=spec;mapRenderViewRow();mapRenderItems();mapSchedulePreview(500)}}return}
 const el=e.target.closest('[data-map-item],[data-map-box],[data-map-prop="scale_km"],[data-map-prop="year"]');if(!el||!mapEd.spec)return;
 if(el.dataset.mapBox!==undefined){const n=Number(el.value);if(!Number.isFinite(n))return;mapEd.spec.view[Number(el.dataset.mapBox)]=n;mapWrite();return}
 if(el.dataset.mapProp==='year'){const n=Number(el.value);const [low,high]=mapEd.options?.years||[-3400,2024];if(el.value===''||!Number.isInteger(n)||n<low||n>high)return;mapEd.spec.year=n;const name=document.querySelector('.map-year-name');if(name)name.textContent=mapYearName(n);mapWrite();mapLoadPolities(n).then(()=>mapRenderItems());return}
 if(el.dataset.mapProp==='scale_km'){const n=Number(el.value);if(n>0)mapEd.spec.scale_km=n;else delete mapEd.spec.scale_km;mapWrite();return}
 const sel=mapEd.selected,item=sel&&mapEd.spec[sel.group]?.[sel.index];if(!item)return;const key=el.dataset.mapItem;
 if(['label','text'].includes(key)){item[key]=el.value;mapWrite();return}
 if(key.startsWith('offset')&&el.value===''){delete item.offset;mapWrite();return}
 if(el.type==='number'){const n=Number(el.value);if(el.value===''||!Number.isFinite(n))return;if(key.startsWith('offset'))item.offset??=[90,-70];mapSetPath(item,key,n);mapWrite();return}
});
document.addEventListener('change',e=>{
 const el=e.target;if(!mapEd.spec||!el.closest?.('.map-editor'))return;const sel=mapEd.selected,item=sel&&mapEd.spec[sel.group]?.[sel.index];
 if(el.dataset.mapProp==='view'){const box=mapBox(mapEd.spec)||[-170,-58,180,78];mapEd.spec.view=el.value==='custom'?box.slice():el.value;mapRenderViewRow();mapWrite();return}
 if(el.dataset.mapProp==='era'){mapSetEra(el.value);mapRenderViewRow();mapRenderItems();mapWrite();mapLoadPolities(mapEd.spec.year).then(()=>mapRenderItems());return}
 if(el.dataset.mapProp==='ma'){mapEd.spec.ma=Number(el.value);mapWrite();return}
 if(el.dataset.mapProp==='paleo'){if(el.value==='margin')delete mapEd.spec.paleo;else mapEd.spec.paleo=el.value;mapWrite();return}
 if(el.dataset.mapFlag){const key=el.dataset.mapFlag;if(el.checked)mapEd.spec[key]=key==='land'?'white':true;else delete mapEd.spec[key];mapWrite();return}
 if(el.matches('[data-map-add]')){const group=el.value;if(!group)return;(mapEd.spec[group]??=[]).push(mapNewItem(group));mapEd.selected={group,index:mapEd.spec[group].length-1};mapEd.vertex=null;mapRenderItems();mapWrite();return}
 if(el.dataset.mapAddPlace&&item&&el.value){(item[el.dataset.mapAddPlace]??=[]).push(el.value);mapRenderItems();mapWrite();return}
 if(!item)return;const key=el.dataset.mapItem;
 if(key==='side'){if(el.value==='right')delete item.side;else item.side=el.value}
 else if(key==='pattern')item.pattern=el.value;
 else if(['open','dash'].includes(key)){if(el.checked)item[key]=true;else delete item[key]}
 else if(key==='present'){if(el.checked)item.present=true;else delete item.present;mapRenderItems()}
 else if(key==='unit'){for(const k of Object.keys(mapShadeUnits))delete item[k];item[el.value]=[];mapRenderItems()}
 else if(key==='arrow'){if(el.checked)delete item.arrow;else item.arrow=false}
 else if(key==='axis'){const value=item.lat??item.lon??0;delete item.lat;delete item.lon;item[el.value]=value;mapRenderItems()}
 else return;
 mapWrite();
});
document.addEventListener('click',e=>{
 const btn=e.target.closest('[data-map-action],[data-map-select],[data-map-remove-place]');if(!btn)return;
 if(state.job?.status==='running'){toast('생성 작업이 끝난 뒤 편집하세요.');return}
 const act=btn.dataset.mapAction;
 if(act==='start'||act==='reset'){mapStart();return}
 if(act==='strict'){const mode=document.querySelector('[data-field="image_mode"]');if(mode){mode.value='strict';mode.dispatchEvent(new Event('input',{bubbles:true}))}render();return}
 if(btn.dataset.mapSelect){const [group,index]=btn.dataset.mapSelect.split(':');mapEd.selected={group,index:Number(index)};mapEd.vertex=null;mapDraw();mapRenderItems();return}
 const sel=mapEd.selected,item=sel&&mapEd.spec?.[sel.group]?.[sel.index];if(!item)return;
 if(btn.dataset.mapRemovePlace){for(const key of ['countries','provinces','districts','polities'])if(item[key])item[key]=item[key].filter(x=>x!==btn.dataset.mapRemovePlace);mapRenderItems();mapWrite();return}
 if(act==='remove'){mapEd.spec[sel.group].splice(sel.index,1);if(!mapEd.spec[sel.group].length)delete mapEd.spec[sel.group];mapEd.selected=null;mapEd.vertex=null}
 if(act==='remove-vertex'){const list=sel.group==='routes'?item.path:item.points,min=sel.group==='routes'?2:3;if(list.length<=min){toast(`${mapGroups[sel.group]}에는 꼭짓점이 ${min}개 이상 있어야 합니다.`);return}list.splice(mapEd.vertex,1);mapEd.vertex=null}
 mapDraw();mapRenderItems();mapWrite();
});

// 그림 계획 칸 바로 아래에 편집 화면을 붙인다. 화면은 통째로 다시 그려지므로 새로 생긴 편집 영역을 찾아 연결한다.
const mapBaseImagePlanFields=imagePlanFields;
imagePlanFields=function(c){
 const html=mapBaseImagePlanFields(c);
 if(html.includes('image-plan-readonly'))return mapIsSpec(c.image_locked)?html+mapEditorHtml(c,true):html;
 const extra=mapIsSpec(c.image_locked)?mapEditorHtml(c,false):['사회','과학'].includes(mapSubjectGroup())?mapStartHtml(c):'';
 if(!extra)return html;
 const end=html.indexOf('</label>',html.indexOf('id="lockedField"'));
 return end<0?html+extra:html.slice(0,end+8)+extra+html.slice(end+8);
};
new MutationObserver(()=>{for(const section of document.querySelectorAll('.map-editor:not([data-map-ready])'))mapInit(section)}).observe(document.body,{childList:true,subtree:true});

'use strict';
// Presentation layer for the existing vector/text editor. Editing state and
// commands remain owned by designer.js, vectors.js, layers.js and snapping.js.
const uxDesignerPrefs={layersCollapsed:false,propertiesCollapsed:false,mobilePanel:'canvas'};
const uxDesignerMoreActions=new Set(['all','copy','paste']);
const uxDesignerMoreVectorActions=new Set(['flipx','flipy','lock','visible','ungroup']);

function uxDesignerShell(){return $('#designerShell')}
function uxDesignerToolbar(){return $('#designerObjectToolbar')}
function uxDesignerEnsurePanels(){
 const shell=uxDesignerShell();if(!shell)return;
 // ux-minimal.js supplied an earlier pair of fold buttons. This module owns
 // the fold state together with the mobile panel switcher.
 shell.querySelectorAll('[data-designer-panel]').forEach(button=>button.remove());
 const top=shell.querySelector('.designer-top');if(!top)return;
 const insertBeforeToolbar=node=>top.insertBefore(node,uxDesignerToolbar()||null);
 let nav=$('#uxDesignerMobilePanels');
 if(!nav){
  nav=document.createElement('div');nav.id='uxDesignerMobilePanels';nav.className='designer-mobile-panels';nav.setAttribute('role','tablist');nav.setAttribute('aria-label','편집 화면');
  nav.innerHTML=[['canvas','캔버스'],['layers','레이어'],['properties','속성']].map(([key,label])=>`<button type="button" role="tab" data-ux-designer-panel="${key}" aria-controls="${key==='canvas'?'designerCanvasPanel':key==='layers'?'designerLayersPanel':'designerInspectorPanel'}">${label}</button>`).join('');
  insertBeforeToolbar(nav);
 }
 const addFold=(key,label)=>{
  let button=top.querySelector(`[data-ux-designer-collapse="${key}"]`);
  if(!button){button=document.createElement('button');button.type='button';button.className='small-btn designer-fold-toggle';button.dataset.uxDesignerCollapse=key;insertBeforeToolbar(button)}
  button.setAttribute('aria-controls',key==='layers'?'designerLayersPanel':'designerInspectorPanel');
  button.setAttribute('aria-expanded',String(!uxDesignerPrefs[key+'Collapsed']));
  button.textContent=`${label} ${uxDesignerPrefs[key+'Collapsed']?'펼치기':'접기'}`;
 };
 addFold('layers','레이어');addFold('properties','속성');
 const layers=shell.querySelector('.designer-layers'),inspector=shell.querySelector('.designer-inspector'),center=shell.querySelector('.designer-center');
 if(layers){layers.id='designerLayersPanel';layers.setAttribute('role','tabpanel');layers.setAttribute('aria-label','레이어')}
 if(inspector){inspector.id='designerInspectorPanel';inspector.setAttribute('role','tabpanel');inspector.setAttribute('aria-label','속성')}
 if(center){center.id='designerCanvasPanel';center.setAttribute('role','tabpanel');center.setAttribute('aria-label','캔버스')}
 const heading=(panel)=>{
  if(!panel)return;
  let h=panel.querySelector(':scope > .designer-panel-heading');
  if(!h){const old=panel.querySelector(':scope > h3');if(!old)return;h=document.createElement('div');h.className='designer-panel-heading';old.replaceWith(h);h.append(old)}
 };
 heading(layers);heading(inspector);
 shell.dataset.layersCollapsed=String(uxDesignerPrefs.layersCollapsed);
 shell.dataset.propertiesCollapsed=String(uxDesignerPrefs.propertiesCollapsed);
 shell.dataset.mobilePanel=uxDesignerPrefs.mobilePanel;
 nav.querySelectorAll('[role="tab"]').forEach(tab=>{
  const selected=tab.dataset.uxDesignerPanel===uxDesignerPrefs.mobilePanel;
  tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
 });
}

function uxDesignerRestoreMore(toolbar){
 const menu=toolbar?.querySelector('#designerMoreActions');if(!menu)return;
 for(const button of [...menu.querySelectorAll('[data-ux-more-kind]')]){
  const target=button.dataset.uxMoreKind==='design'?'#designerEditActions':'#designerArrangeActions';
  const group=$(target);if(group){button.removeAttribute('data-ux-more-kind');group.append(button)}
 }
}
function uxDesignerEnsureMore(toolbar){
 let details=toolbar.querySelector('#designerMoreMenu');
 if(!details){
  details=document.createElement('details');details.id='designerMoreMenu';details.className='designer-more-menu';
  details.innerHTML='<summary aria-label="보조 편집 도구">⋯ 더보기</summary><div id="designerMoreActions" class="object-action-group" aria-label="보조 편집 도구"></div>';
  toolbar.append(details);
 }
 return details.querySelector('#designerMoreActions');
}
function uxDesignerSelectionToolbar(){
 const toolbar=uxDesignerToolbar();if(!toolbar)return;
 uxDesignerEnsurePanels();
 const more=uxDesignerEnsureMore(toolbar);
 for(const button of toolbar.querySelectorAll('[data-design-action]'))if(uxDesignerMoreActions.has(button.dataset.designAction)){
  button.dataset.uxMoreKind='design';more.append(button);
 }
 for(const button of toolbar.querySelectorAll('[data-vector-action]'))if(uxDesignerMoreVectorActions.has(button.dataset.vectorAction)){
  button.dataset.uxMoreKind='vector';more.append(button);
 }
 const shapes=ve.selected.size,labels=designer.labels.size,total=shapes+labels;
 const shapeOnly=shapes>0&&labels===0,labelOnly=labels>0&&shapes===0,mixed=shapes>0&&labels>0;
 toolbar.dataset.selection=mixed?'mixed':shapeOnly?(shapes===1?'shape':'shapes'):labelOnly?(labels===1?'label':'labels'):'none';
 toolbar.hidden=total===0;
 const setVisible=(selector,visible)=>toolbar.querySelectorAll(selector).forEach(button=>button.hidden=!visible);
 setVisible('[data-design-action="duplicate"],[data-design-action="delete"]',total>0);
 setVisible('[data-vector-action="front"],[data-vector-action="back"]',shapeOnly);
 setVisible('[data-vector-action="group"]',shapeOnly&&shapes>1);
 setVisible('[data-vector-action="ungroup"]',shapeOnly&&shapes===1);
 setVisible('#designerMoreActions [data-vector-action="flipx"],#designerMoreActions [data-vector-action="flipy"],#designerMoreActions [data-vector-action="lock"],#designerMoreActions [data-vector-action="visible"]',shapeOnly);
 setVisible('[data-rotate-step]',shapeOnly);
 setVisible('[data-design-align]',total>0);
 const distribute=total>=3;
 setVisible('[data-design-align^="distribute"]',distribute);
 const hasMore=!!more.querySelector('button');
 const details=$('#designerMoreMenu');if(details)details.hidden=total===0||!hasMore;
 for(const group of toolbar.querySelectorAll('.object-action-group'))group.hidden=!group.querySelector('button:not([hidden])');
 const align=toolbar.querySelector('.object-align-menu');if(align)align.hidden=total===0;
}

function uxDesignerChoosePanel(key){
 if(!['canvas','layers','properties'].includes(key))return;
 uxDesignerPrefs.mobilePanel=key;uxDesignerEnsurePanels();
}
function uxDesignerSetCollapse(key){
 const prop=key==='layers'?'layersCollapsed':'propertiesCollapsed';uxDesignerPrefs[prop]=!uxDesignerPrefs[prop];
 uxDesignerEnsurePanels();if(ve.expanded)vzoom();
}

const uxDesignerBaseObjectToolbar=designObjectToolbar;
designObjectToolbar=function(){
 const toolbar=uxDesignerToolbar();if(toolbar)uxDesignerRestoreMore(toolbar);
 uxDesignerBaseObjectToolbar();uxDesignerSelectionToolbar();
};
const uxDesignerBasePanels=designPanels;
designPanels=function(){uxDesignerBasePanels();uxDesignerEnsurePanels();uxDesignerSelectionToolbar()};
const uxDesignerBaseInit=initVectorEditor;
initVectorEditor=function(){uxDesignerBaseInit();uxDesignerEnsurePanels();uxDesignerSelectionToolbar()};

document.addEventListener('click',event=>{
 const tab=event.target.closest('[data-ux-designer-panel]');
 if(tab){event.preventDefault();uxDesignerChoosePanel(tab.dataset.uxDesignerPanel);return}
 const fold=event.target.closest('[data-ux-designer-collapse]');
 if(fold){event.preventDefault();uxDesignerSetCollapse(fold.dataset.uxDesignerCollapse)}
});
document.addEventListener('keydown',event=>{
 const tab=event.target.closest('#uxDesignerMobilePanels [role="tab"]');if(!tab)return;
 const tabs=[...$('#uxDesignerMobilePanels').querySelectorAll('[role="tab"]')],at=tabs.indexOf(tab);
 const next=event.key==='ArrowRight'?(at+1)%tabs.length:event.key==='ArrowLeft'?(at+tabs.length-1)%tabs.length:-1;
 if(next>=0){event.preventDefault();tabs[next].focus();uxDesignerChoosePanel(tabs[next].dataset.uxDesignerPanel)}
});

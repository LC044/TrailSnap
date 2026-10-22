// Scroll-linked scenes are mounted only in the browser and cleaned up on navigation.
export function initHome(root, options = {}) {
  let disposed = false;
  const controller = new AbortController();
  const originalOverflow = window.document.body.style.overflow;
  const document = {
    querySelector: root.querySelector.bind(root), querySelectorAll: root.querySelectorAll.bind(root),
    getElementById: id => root.querySelector('#' + id), body: window.document.body,
    documentElement: root, fonts: window.document.fonts,
  };
  const listen = (target, name, handler, options = {}) => target.addEventListener(name, handler, {...options, signal: controller.signal});


const fitDesktopPreviews=()=>{
  document.querySelectorAll('.desktop-viewport').forEach(viewport=>{
    const frame=viewport.querySelector('iframe');
    const expanded=Boolean(viewport.closest('.expanded'));
    const width=viewport.clientWidth;
    if(!width)return;
    // Expanded phone windows use the product's native mobile layout for readable interaction.
    const nativeMobile=(expanded || Boolean(viewport.closest('.memory-panel'))) && window.innerWidth<768;
    const logicalWidth=nativeMobile?width:Math.max(1440,expanded?width:0);
    const scale=width/logicalWidth;
    const fillWindow=expanded || Boolean(viewport.closest('.hero-window,.memory-panel'));
    const logicalHeight=fillWindow?Math.round(viewport.clientHeight/scale):900;
    frame.style.width=logicalWidth+'px';frame.style.height=logicalHeight+'px';
    frame.style.setProperty('--preview-scale',String(scale));
    viewport.querySelectorAll('iframe').forEach(other=>{
      if(other.id==='city-showcase-frame'){
        other.style.width=width+'px';other.style.height=viewport.clientHeight+'px';other.style.setProperty('--preview-scale','1');
      }else if(other!==frame)other.style.cssText=frame.style.cssText;
    });
  });
};
const previewObserver=new ResizeObserver(fitDesktopPreviews);
document.querySelectorAll('.desktop-viewport').forEach(viewport=>previewObserver.observe(viewport));
listen(window,'resize',fitDesktopPreviews);
fitDesktopPreviews();

const demoOrigin='https://demo.siyuan.ink';
const homeFrame=document.getElementById('live-home');

document.querySelectorAll('[data-reload]').forEach(button=>button.addEventListener('click',()=>{
  const frame=document.getElementById(button.dataset.reload);frame.src=frame.getAttribute('src');
}));
document.querySelectorAll('[data-expand]').forEach(button=>button.addEventListener('click',()=>{
  const shell=document.getElementById(button.dataset.expand);
  const expanded=shell.classList.toggle('expanded');button.textContent=expanded?'退出全屏 ×':'全屏查看';button.setAttribute('aria-expanded',String(expanded));
  if(shell.id==='live-map-shell'){shell.style.width='';shell.style.right='';shell.style.top='';shell.style.transform='';measureScene();}
  document.body.style.overflow=document.querySelector('.live-shell.expanded')?'hidden':'';
}));
listen(window,'keydown',event=>{if(event.key==='Escape'){document.querySelectorAll('.live-shell.expanded').forEach(shell=>{shell.classList.remove('expanded');const button=shell.querySelector('[data-expand]');button.textContent='全屏查看';button.setAttribute('aria-expanded','false');});document.body.style.overflow='';measureScene();}});

// Scroll distance drives progress directly; scrolling back reverses the same sequence.
const motionPreference=window.matchMedia('(min-width:1001px) and (prefers-reduced-motion:no-preference)');
const scene=document.querySelector('.scroll-scene');
const stage=document.querySelector('.hero');
const heroCopy=document.querySelector('.hero-copy');
const heroLive=document.querySelector('.hero-live');
const sceneCaption=document.querySelector('.scene-caption');
const sceneProgress=document.querySelector('.scene-progress span');

const revealElements=[...document.querySelectorAll('.cap-heading,.cap-grid article,.start-grid article,.tools-heading,.tool-showcase,.trust-heading,.trust-grid article,.end')];
revealElements.forEach(el=>el.setAttribute('data-reveal',''));
const featureElements=[...document.querySelectorAll('.motion-feature')];
const clamp01=value=>Math.max(0,Math.min(1,value));
const ease=value=>value*value*(3-2*value);
let sceneGeometry=null,scrollFrame=0;
function measureScene(){
  heroLive.style.transform='';
  const stageRect=stage.getBoundingClientRect(),liveRect=heroLive.getBoundingClientRect();
  const availableHeight=Math.max(200,stageRect.height-150);
  const targetWidth=Math.min(1440,stageRect.width-104,availableHeight*1.6);
  sceneGeometry={x:stageRect.left+stageRect.width/2-(liveRect.left+liveRect.width/2),y:stageRect.top+stageRect.height/2-25-(liveRect.top+liveRect.height/2),scale:Math.max(1,targetWidth/liveRect.width)};
  measureFeatureScenes();
  updateScrollScene();
}
function updateScrollScene(){
  scrollFrame=0;
  if(!motionPreference.matches){
    heroLive.style.transform='';heroCopy.style.transform='';heroCopy.style.opacity='';heroCopy.inert=false;
    featureElements.forEach(el=>{const panel=el.querySelector('.live-shell');panel.style.transform='';panel.style.width='';panel.style.right='';panel.style.top='';el.querySelector('.live-section-heading').style.opacity='';el.querySelector('.live-section-heading').style.transform='';});
    return;
  }
  const top=scene.getBoundingClientRect().top;
  const progress=clamp01((81-top)/Math.max(1,scene.offsetHeight-stage.offsetHeight));
  const zoom=ease(clamp01((progress-.06)/.65));
  const copyExit=ease(clamp01((progress-.04)/.3));
  heroCopy.style.opacity=String(1-copyExit);
  heroCopy.style.transform=`translate3d(${-copyExit*85}px,${-copyExit*30}px,0)`;
  heroCopy.inert=copyExit>.97;
  if(sceneGeometry)heroLive.style.transform=`translate3d(${sceneGeometry.x*zoom}px,${sceneGeometry.y*zoom}px,0) scale(${1+(sceneGeometry.scale-1)*zoom})`;
  sceneCaption.style.opacity=String(ease(clamp01((progress-.69)/.16)));
  sceneCaption.style.transform=`translateY(${(1-ease(clamp01((progress-.69)/.16)))*18}px)`;
  sceneProgress.style.transform=`scaleX(${progress})`;
  revealElements.forEach(el=>{
    const rect=el.getBoundingClientRect();
    const naturalTop=rect.top-(parseFloat(el.style.getPropertyValue('--reveal-y'))||0);
    const fraction=ease(clamp01((innerHeight*.97-naturalTop)/(innerHeight*.29)));
    el.style.setProperty('--reveal-opacity',String(.12+.88*fraction));
    el.style.setProperty('--reveal-y',`${(1-fraction)*38}px`);
  });
  updateFeatureScenes();
  updateMemoryScene();
}
function queueScrollUpdate(){if(!scrollFrame)scrollFrame=requestAnimationFrame(updateScrollScene);}
function resetMotion(){document.documentElement.classList.toggle('motion-ready',motionPreference.matches);measureScene();}
listen(window,'scroll',queueScrollUpdate,{passive:true});
listen(window,'resize',resetMotion);
listen(motionPreference,'change',resetMotion);


const featureGeometry=new Map();
function measureFeatureScenes(){
  featureElements.forEach(el=>{
    const panel=el.querySelector('.live-shell');panel.style.transform='';panel.style.width='';panel.style.right='';panel.style.top='';
    const box=el.getBoundingClientRect(),rect=panel.getBoundingClientRect();
    const width=Math.min(1200,box.width,(box.height-145)*1.6);
    featureGeometry.set(el,{startWidth:rect.width,targetWidth:Math.max(rect.width,width),stageWidth:box.width,stageHeight:box.height});
  });
}
function updateFeatureScenes(){
  featureElements.forEach(el=>{
    const wrapper=el.parentElement,panel=el.querySelector('.live-shell'),heading=el.querySelector('.live-section-heading');
    const progress=clamp01((81-wrapper.getBoundingClientRect().top)/Math.max(1,wrapper.offsetHeight-el.offsetHeight));
    const zoom=ease(clamp01((progress-.04)/.66));
    const exit=ease(clamp01((progress-.02)/.32));
    const geometry=featureGeometry.get(el);
    heading.style.opacity=String(1-exit);
    heading.style.transform=`translateY(-50%) translate3d(${-exit*60}px,${-exit*20}px,0)`;
    if(geometry&&!panel.classList.contains('expanded')){
      // Lay out at the actual rendered size: text and canvases never get bitmap-scaled.
      panel.style.width=Math.round(geometry.startWidth+(geometry.targetWidth-geometry.startWidth)*zoom)+'px';
      panel.style.right=Math.round((geometry.stageWidth-geometry.targetWidth)/2*zoom)+'px';
      panel.style.top=Math.round(geometry.stageHeight/2-18*zoom-panel.offsetHeight/2)+'px';
      panel.style.transform='none';
    }
    el.style.setProperty('--feature-caption',String(ease(clamp01((progress-.68)/.2))));
    el.style.setProperty('--feature-progress',String(progress));
  });
  document.querySelectorAll('.cap-grid article').forEach(el=>{
    const offset=parseFloat(el.style.getPropertyValue('--reveal-y'))||0;
    el.style.setProperty('--card-tilt',`${offset/38*7}deg`);
  });
}


const memoryScene=document.querySelector('.memory-scene');
const memoryStage=document.querySelector('.memory-stage');
let memoryPage=0;
function setMemoryPage(index){
  memoryPage=index;
  document.querySelectorAll('[data-memory-tab]').forEach(button=>{const active=Number(button.dataset.memoryTab)===index;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
  document.querySelectorAll('[data-memory-copy]').forEach(copy=>{const active=Number(copy.dataset.memoryCopy)===index;copy.hidden=!active;copy.classList.toggle('is-active',active);});
  document.querySelectorAll('.memory-panel').forEach((panel,i)=>{const active=i===index;panel.classList.toggle('is-active',active);panel.inert=!active;panel.setAttribute('aria-hidden',String(!active));});
  document.getElementById('memory-page-label').textContent=`0${index+1} / 03 · ${['人生章节','月迹','票夹'][index]}`;
}
function updateMemoryScene(){
  if(!motionPreference.matches)return;
  const progress=clamp01((81-memoryScene.getBoundingClientRect().top)/Math.max(1,memoryScene.offsetHeight-memoryStage.offsetHeight));
  const index=Math.min(2,Math.floor(progress*3));
  if(index!==memoryPage)setMemoryPage(index);
  memoryScene.style.setProperty('--memory-progress',String(progress));
  memoryScene.style.setProperty('--chapter-progress',String(clamp01(progress*3-index)));
}
function chooseMemory(index){
  if(motionPreference.matches){const top=scrollY+memoryScene.getBoundingClientRect().top-81;const distance=memoryScene.offsetHeight-memoryStage.offsetHeight;window.scrollTo({top:top+distance*(index/3+.035),behavior:'smooth'});}else{setMemoryPage(index);memoryScene.style.setProperty('--chapter-progress','1');}
}
document.querySelectorAll('[data-memory-tab]').forEach(button=>{
  button.addEventListener('click',()=>chooseMemory(Number(button.dataset.memoryTab)));
  button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=event.key==='Home'?0:event.key==='End'?2:(memoryPage+(event.key==='ArrowRight'?1:2))%3;chooseMemory(index);document.getElementById('memory-tab-'+index).focus();});
});
document.querySelectorAll('[data-jump-memory]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();if(!motionPreference.matches)memoryScene.scrollIntoView({behavior:'smooth'});chooseMemory(Number(link.dataset.jumpMemory));}));
function selectMapView(view){
  options.setMapView?.(view);
  fitDesktopPreviews();
}

document.querySelectorAll('[data-map-view]').forEach(button=>{button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const views=['3d','city','puzzle'];const current=views.indexOf(button.dataset.mapView);const view=event.key==='Home'?'3d':event.key==='End'?'puzzle':views[(current+(event.key==='ArrowRight'?1:2))%3];selectMapView(view);document.getElementById('map-view-'+view).focus();});});
document.querySelectorAll('[data-jump-map]').forEach(link=>link.addEventListener('click',()=>selectMapView(link.dataset.jumpMap)));

resetMotion();
if(document.fonts)document.fonts.ready.then(() => { if (!disposed) measureScene() });


  return () => { disposed = true; controller.abort(); previewObserver.disconnect(); cancelAnimationFrame(scrollFrame); root.classList.remove('motion-ready'); window.document.body.style.overflow = originalOverflow; };
}

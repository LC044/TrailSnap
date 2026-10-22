const root=document.getElementById('fragment');
const kind=document.body.dataset.kind;
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const image=(src,alt,extra='')=>`<img src="${escapeHTML(src)}" alt="${escapeHTML(alt)}" ${extra}>`;
const reduced=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;
function syncTheme(){
  try{document.body.classList.toggle('dark',parent.document.documentElement.classList.contains('dark'));}catch{}
  window.dispatchEvent(new Event('fragment-theme'));
}
syncTheme();
try{new MutationObserver(syncTheme).observe(parent.document.documentElement,{attributes:true,attributeFilter:['class']});}catch{}
const getData=async()=>{const response=await fetch('./showcase-data.json');if(!response.ok)throw new Error('data');return response.json();};
async function renderCity(data){
  root.innerHTML='<div class="city-map"><div class="city-chart" id="city-chart" aria-label="演示相册中的城市点亮记录"></div><div class="city-legend"><span><i></i>有照片记录</span><span><i></i>暂无记录</span></div><div class="map-controls"><button id="map-in" aria-label="放大地图">+</button><button id="map-out" aria-label="缩小地图">−</button><button id="map-reset">复位</button></div></div>';
  const response=await fetch('./city-geo.json');if(!response.ok)throw new Error('map');const geo=await response.json();
  echarts.registerMap('trailsnap-cities',geo);
  const chart=echarts.init(document.getElementById('city-chart'),null,{renderer:'canvas'});
  function draw(){
    const css=getComputedStyle(document.body),dark=document.body.classList.contains('dark');
    const color=key=>css.getPropertyValue(key).trim();
    const values=data.distribution.map(item=>({name:item.name,value:item.count}));
    const max=Math.max(...values.map(item=>item.value),1);
    chart.setOption({animation:!reduced(),animationDuration:900,backgroundColor:'transparent',tooltip:{trigger:'item',renderMode:'richText',formatter:params=>`${params.name}\n${Number.isFinite(params.value)&&params.value>0?params.value+' 张照片':'暂无照片记录'}`,backgroundColor:color('--paper'),textStyle:{color:color('--ink'),fontSize:13},borderColor:color('--line')},visualMap:{show:false,min:1,max,inRange:{color:dark?['#4c6554','#769780','#aac4ad']:['#b5cab8','#789f82','#456854']}},series:[{type:'map',map:'trailsnap-cities',roam:true,scaleLimit:{min:.7,max:5},zoom:1.05,layoutCenter:['50%','46%'],layoutSize:'105%',data:values,selectedMode:'single',label:{show:true,formatter:p=>p.value>0?p.name:'',color:color('--primary'),fontSize:10},labelLayout:{hideOverlap:true},itemStyle:{areaColor:color('--soft'),borderColor:dark?'#45574a':'#cad6cb',borderWidth:.6},emphasis:{label:{color:color('--ink')},itemStyle:{areaColor:dark?'#91b099':'#c3d6bf'}},select:{itemStyle:{areaColor:dark?'#b3c9a9':'#b5cba8'}}}]},true);
  }
  function zoom(factor){const state=chart.getOption().series[0];chart.setOption({series:[{zoom:Math.max(.7,Math.min(5,(state.zoom||1)*factor))}]});}
  document.getElementById('map-in').onclick=()=>zoom(1.3);document.getElementById('map-out').onclick=()=>zoom(1/1.3);document.getElementById('map-reset').onclick=draw;
  window.addEventListener('fragment-theme',draw);new ResizeObserver(()=>chart.resize()).observe(root);draw();
}

const phasePaths={first_quarter:'M24 5a19 19 0 0 1 0 38z',last_quarter:'M24 5a19 19 0 0 0 0 38z',waxing_crescent:'M24 5a19 19 0 1 1 0 38c8-5 11-12 11-19S32 10 24 5z',waxing_gibbous:'M24 5a19 19 0 1 1 0 38c-5-5-7-12-7-19s2-14 7-19z',waning_gibbous:'M24 5a19 19 0 1 0 0 38c5-5 7-12 7-19s-2-14-7-19z',waning_crescent:'M24 5a19 19 0 1 0 0 38c-8-5-11-12-11-19S16 10 24 5z'};
function phaseIcon(phase,label){return `<svg viewBox="0 0 48 48" role="img" aria-label="${escapeHTML(label)}"><circle cx="24" cy="24" r="20" fill="#111a17" stroke="#64756a" stroke-width="1.5"/>${phase==='full_moon'?'<circle cx="24" cy="24" r="19" fill="#f3f5ef"/>':phasePaths[phase]?`<path d="${phasePaths[phase]}" fill="#f3f5ef"/>`:''}</svg>`;}
function renderSwipe(data){
  const photos=data.days.items.flatMap(d=>d.photos.map(p=>({...p,day:d.day}))).slice(0,10);let index=0,history=[],busy=false,startX=null;
  root.innerHTML='<div class="swipe-demo"><div class="swipe-top"><span id="swipe-count"></span><button id="swipe-undo" aria-label="撤销上一次选择">↶ 撤销</button></div><div class="swipe-stack"><div class="swipe-card" id="swipe-card" tabindex="0" role="group" aria-label="左右拖动照片，或使用左右方向键选择"><img id="swipe-image" alt="演示照片" draggable="false"><small id="swipe-date"></small><span class="swipe-tag" id="swipe-tag"></span></div><div class="swipe-complete" id="swipe-complete" hidden><h3>这组示例，整理好了。</h3><p class="small-note" id="swipe-summary"></p><button id="swipe-reset">再体验一次</button></div></div><div class="swipe-actions"><button id="swipe-left">← 丢弃</button><button id="swipe-right">保留 ♡</button></div><p class="swipe-status" id="swipe-status" role="status">向左丢弃，向右保留 · 仅演示，不会删除照片</p></div>';
  const card=document.getElementById('swipe-card'),tag=document.getElementById('swipe-tag');
  function draw(){const complete=index>=photos.length;card.hidden=complete;document.getElementById('swipe-complete').hidden=!complete;document.getElementById('swipe-left').disabled=complete;document.getElementById('swipe-right').disabled=complete;document.getElementById('swipe-undo').disabled=!history.length;document.getElementById('swipe-count').textContent=`照片筛选 · ${Math.min(index+1,photos.length)} / ${photos.length}`;if(!complete){document.getElementById('swipe-image').src=photos[index].src;document.getElementById('swipe-date').textContent=photos[index].day;}else{document.getElementById('swipe-summary').textContent=`保留 ${history.filter(h=>h.direction>0).length} 张 · 丢弃 ${history.filter(h=>h.direction<0).length} 张`;}card.style.transform='';card.style.transition='';tag.style.opacity=0;}
  function choose(direction){if(busy||index>=photos.length)return;busy=true;card.style.transition=reduced()?'none':'transform .2s ease,opacity .2s ease';card.style.transform=`translateX(${direction*350}px) rotate(${direction*20}deg)`;tag.textContent=direction>0?'保留':'丢弃';tag.style.opacity=1;setTimeout(()=>{history.push({index,direction});index++;busy=false;document.getElementById('swipe-status').textContent='已在本地演示中'+(direction>0?'保留':'丢弃')+'这一张，可撤销；不会修改相册。';draw();},reduced()?0:200);}
  document.getElementById('swipe-left').onclick=()=>choose(-1);document.getElementById('swipe-right').onclick=()=>choose(1);
  document.getElementById('swipe-undo').onclick=()=>{if(busy||!history.length)return;index=history.pop().index;draw();document.getElementById('swipe-status').textContent='已撤销上一次本地选择。';};
  document.getElementById('swipe-reset').onclick=()=>{index=0;history=[];draw();};
  card.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();choose(event.key==='ArrowRight'?1:-1);}});
  card.addEventListener('pointerdown',event=>{if(busy)return;startX=event.clientX;card.setPointerCapture(event.pointerId);card.focus({preventScroll:true});});
  card.addEventListener('pointermove',event=>{if(startX===null||busy)return;const dx=event.clientX-startX;card.style.transform=`translateX(${dx}px) rotate(${dx/18}deg)`;tag.textContent=dx>0?'保留':'丢弃';tag.style.opacity=Math.min(1,Math.abs(dx)/90);});
  card.addEventListener('pointerup',event=>{if(startX===null)return;const delta=event.clientX-startX;startX=null;if(Math.abs(delta)>65)choose(delta>0?1:-1);else draw();});
  card.addEventListener('pointercancel',()=>{startX=null;draw();});draw();
}

try{const data=await getData();const handlers={city:renderCity,swipe:renderSwipe};await handlers[kind](data);}catch(error){root.innerHTML='<p class="error" role="alert">展示内容暂时无法打开，请刷新重试，或通过上方链接访问演示站。</p>';console.error('Showcase load failed:',error);}

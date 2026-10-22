// Curated, fictional website samples. This module makes no network requests.
export function initFixedSamples(root) {
  const document = { getElementById: id => root.querySelector('#' + id) };
  const pages=[
    {date:'2025.10.03',short:'10 / 03',weekday:'星期五',place:'湖畔 · 山间小屋',title:'在湖边，浪费一个下午。',photos:['lake.jpg','mountain.jpg','forest.jpg'],moment:'forest.jpg',caption:['早上推开窗，湖面还浮着一层薄雾。远处的山安静地站着，小屋的倒影落在水里，像一张没有写完的明信片。','我们沿着湖边慢慢走，没有查下一站的攻略。风吹过来，树叶沙沙响，拍照的人停下来，等走在前面的人回头。','后来才发现，这一天最喜欢的照片，都不是刻意摆好的姿势。是一起看过的山，是路边的光，也是我们终于愿意慢下来。'],note:'湖畔散步 / 山间小屋 / 一起出发的人'},
    {date:'2025.10.04',short:'10 / 04',weekday:'星期六',place:'山野 · 森林步道',title:'走进森林，把声音调小。',photos:['forest.jpg','lake.jpg','mountain.jpg'],moment:'mountain.jpg',caption:['走进树林的时候，手机只剩下一格信号。阳光从树梢漏下来，在苔藓和落叶上画出一小块一小块的亮。','脚下的路有些潮湿，空气里都是草木的味道。偶尔有人停下来拍一棵树，我们就在旁边等，听远处传来的鸟鸣。','返程时翻看照片，才想起上午走了那么久。那些没有赶路的时刻，被安安静静地装进了这本日记。'],note:'森林步道 / 斑驳树影 / 山间空气'},
    {date:'2025.10.05',short:'10 / 05',weekday:'星期日',place:'海边 · 假期最后一天',title:'再看一眼海，然后回家。',photos:['sea.jpg','forest.jpg','lake.jpg'],moment:'sea.jpg',caption:['最后一天，我们把行程留给了海。沙滩上没有太多人，浪一次次涌上来，又把脚印轻轻擦掉。','我们坐在岸边，聊了些回家以后的事。相机里已经装了很多照片，却还是忍不住，再拍下一片云、一阵风和眼前的人。','旅程总要结束，但照片可以慢慢整理。等到下一个忙碌的日子，就再翻开这一页，想起海风吹过来的感觉。'],note:'海边散步 / 看云发呆 / 带着照片回家'}
  ];
  let bookPage=0;
  const book=document.getElementById('fixed-book');
  book.innerHTML='<div class="nb-spread" id="nb-spread" aria-live="polite"></div><nav class="nb-nav" aria-label="翻阅示例日记"><button id="nb-prev" type="button">← 上一页</button><span id="nb-page"></span><button id="nb-next" type="button">下一页 →</button></nav>';
  function renderBook(animate=false){
    const day=pages[bookPage];
    document.getElementById('nb-spread').innerHTML=`<section class="nb-sheet nb-photo-sheet"><div class="nb-running"><span>行影集 · 山海之间</span><span>${day.date}</span></div><div class="nb-date"><strong>${day.short}</strong><span>${day.weekday} · 假期手记</span></div><div class="nb-photos">${day.photos.map((photo,i)=>`<img src="/showcase/assets/${photo}" alt="${['湖光、山色与旅途风景','旅行中的一处风景','旅行中的光影'][i]}" loading="eager">`).join('')}</div><div class="nb-photo-caption">${day.note}</div><span class="nb-number">${String(bookPage*2+1).padStart(2,'0')}</span></section><section class="nb-sheet nb-writing-sheet"><div class="nb-running"><span>${day.date} · 这一天的故事</span><span>✧</span></div><p class="nb-kicker">我的影像日记 · ${day.weekday}</p><h3>${day.title}</h3><div class="nb-prose">${day.caption.map(text=>`<p>${text}</p>`).join('')}</div><div class="nb-moment"><div><span>这一天的片刻</span><strong>${day.place}</strong><small>照片与文字，留在同一页。</small></div><img src="/showcase/assets/${day.moment}" alt="旅途中值得记住的一刻"></div><div class="nb-bottom"><span>示例日记 · 摄影素材 Unsplash</span><span class="nb-number">${String(bookPage*2+2).padStart(2,'0')}</span></div></section>`;
    document.getElementById('nb-prev').disabled=bookPage===0;
    document.getElementById('nb-next').disabled=bookPage===pages.length-1;
    document.getElementById('nb-page').textContent=`山海之间　·　${bookPage+1} / ${pages.length}`;
    const spread=document.getElementById('nb-spread');spread.classList.remove('nb-turning');if(animate){void spread.offsetWidth;spread.classList.add('nb-turning');}
  }
  function turn(direction){const next=bookPage+direction;if(next<0||next>=pages.length)return;bookPage=next;renderBook(true);}
  document.getElementById('nb-prev').onclick=()=>turn(-1);document.getElementById('nb-next').onclick=()=>turn(1);
  book.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();event.stopPropagation();turn(event.key==='ArrowRight'?1:-1);}});
  renderBook();

  const phases=[
    {id:'new',label:'新月',group:'waxing',line:'藏起光芒，等待下一次相遇。',shape:''},
    {id:'crescent',label:'蛾眉月',group:'waxing',line:'一弯细细的光，挂在傍晚。',shape:'M24 5a19 19 0 1 1 0 38c8-5 11-12 11-19S32 10 24 5z'},
    {id:'first',label:'上弦月',group:'waxing',line:'半轮月色，把夜晚照亮。',shape:'M24 5a19 19 0 0 1 0 38z'},
    {id:'gibbous',label:'盈凸月',group:'waxing',line:'比昨天更圆一点，也更明亮。',shape:'M24 5a19 19 0 1 1 0 38c-5-5-7-12-7-19s2-14 7-19z'},
    {id:'full',label:'满月',group:'full',line:'这一晚，月亮刚刚好。',shape:'M24 5a19 19 0 1 1 0 38a19 19 0 1 1 0-38'},
    {id:'waning',label:'亏凸月',group:'waning',line:'圆满之后，也有温柔的留白。',shape:'M24 5a19 19 0 1 0 0 38c5-5 7-12 7-19s-2-14-7-19z'},
    {id:'last',label:'下弦月',group:'waning',line:'留一半月色，给清晨。',shape:'M24 5a19 19 0 0 0 0 38z'},
    {id:'old',label:'残月',group:'waning',line:'一轮将尽，故事还会继续。',shape:'M24 5a19 19 0 1 0 0 38c-8-5-11-12-11-19S16 10 24 5z'}
  ];
  const moon=document.getElementById('fixed-moon');let phaseGroup='all';
  function moonGraphic(phase){const id='sample-moon-'+phase.id;return `<svg viewBox="0 0 48 48" role="img" aria-label="${phase.label}示意"><defs><clipPath id="${id}"><path d="${phase.shape}"/></clipPath></defs><circle cx="24" cy="24" r="19" fill="#18221e" stroke="#3d4e44" stroke-width=".3"/>${phase.shape?`<image href="/showcase/assets/moon-classic.jpg" x="5" y="5" width="38" height="38" clip-path="url(#${id})"/>`:''}</svg>`;}
  moon.innerHTML='<div class="nm-header"><div><span>THE MOON WE KEEP</span><h3>记录每一次阴晴圆缺。</h3><p>从一弯新月，到一轮圆满。</p></div><span class="nm-count">8 种月相</span></div><div class="nm-filters" role="group" aria-label="筛选月相示例"><button data-fixed-phase="all" aria-pressed="true">全部</button><button data-fixed-phase="waxing" aria-pressed="false">渐盈</button><button data-fixed-phase="full" aria-pressed="false">满月</button><button data-fixed-phase="waning" aria-pressed="false">渐亏</button></div><div class="nm-gallery" id="nm-gallery" aria-live="polite"></div><div class="nm-footer"><span>月相示意</span><a href="https://images.nasa.gov/details/PIA00405" target="_blank" rel="noopener">月面素材 NASA / JPL / USGS ↗</a></div>';
  function renderMoon(){moon.querySelectorAll('[data-fixed-phase]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.fixedPhase===phaseGroup)));document.getElementById('nm-gallery').innerHTML=phases.filter(phase=>phaseGroup==='all'||phase.group===phaseGroup).map(phase=>`<article class="nm-phase">${moonGraphic(phase)}<strong>${phase.label}</strong><p>${phase.line}</p></article>`).join('');}
  moon.querySelectorAll('[data-fixed-phase]').forEach(button=>button.onclick=()=>{phaseGroup=button.dataset.fixedPhase;renderMoon();});renderMoon();

  const tickets=[
    {type:'train',kind:'高铁车票',code:'G1026',from:'杭州东',to:'黄山北',date:'2025.10.03',time:'09:20',seat:'二等座 · 06 车 08F',note:'秋日出发 · 山野之间'},
    {type:'train',kind:'高铁车票',code:'G2025',from:'黄山北',to:'上海虹桥',date:'2025.10.05',time:'16:40',seat:'二等座 · 03 车 12A',note:'假期返程 · 满载回忆'},
    {type:'flight',kind:'机票行程',code:'MU2025',from:'上海虹桥',to:'厦门高崎',date:'2025.11.08',time:'14:30',seat:'经济舱 · 18A',note:'下一程 · 去看海吧'}
  ];
  const wallet=document.getElementById('fixed-tickets');let ticketType='all';
  wallet.innerHTML='<div class="nt-header"><div><span>JOURNEYS, COLLECTED.</span><h3>把每一程，收进票夹。</h3></div><span class="nt-count">3 张示例票据</span></div><div class="nt-filters" role="group" aria-label="筛选示例票据"><button data-fixed-ticket="all" aria-pressed="true">全部</button><button data-fixed-ticket="train" aria-pressed="false">火车票</button><button data-fixed-ticket="flight" aria-pressed="false">机票</button></div><div class="nt-list" id="nt-list" aria-live="polite"></div><p class="nt-note">示例票据，非实际出行凭证</p>';
  function renderTickets(){wallet.querySelectorAll('[data-fixed-ticket]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.fixedTicket===ticketType)));document.getElementById('nt-list').innerHTML=tickets.filter(ticket=>ticketType==='all'||ticket.type===ticketType).map(ticket=>`<article class="nt-ticket"><div class="nt-ticket-head"><span>${ticket.kind} / ${ticket.type==='train'?'RAIL':'AIR'}</span><span>${ticket.date}　${ticket.time}</span></div><div class="nt-route"><strong>${ticket.from}</strong><div><b>${ticket.code}</b><span>${ticket.type==='train'?'────────→':'──── ✈ ────'}</span></div><strong>${ticket.to}</strong></div><div class="nt-ticket-foot"><span>${ticket.seat}</span><span>${ticket.note}</span></div></article>`).join('');}
  wallet.querySelectorAll('[data-fixed-ticket]').forEach(button=>button.onclick=()=>{ticketType=button.dataset.fixedTicket;renderTickets();});renderTickets();
}

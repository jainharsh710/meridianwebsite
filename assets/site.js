/* ₹100 time machine: year-end index levels and USD/INR, 2009–2025 */
(function(){
  if(!document.getElementById('tmRange'))return;
  var lastW=null;
  var SPX={2009:1115.10,2010:1257.64,2011:1257.60,2012:1426.19,2013:1848.36,2014:2058.90,2015:2043.94,2016:2238.83,2017:2673.61,2018:2506.85,2019:3230.78,2020:3756.07,2021:4766.18,2022:3839.50,2023:4769.83,2024:5881.63,2025:6845.50};
  var NIFTY={2009:5201.05,2010:6134.50,2011:4624.30,2012:5905.10,2013:6304.00,2014:8282.70,2015:7946.35,2016:8185.80,2017:10530.70,2018:10862.55,2019:12168.45,2020:13981.75,2021:17354.05,2022:18105.30,2023:21731.40,2024:23644.80,2025:26141.85};
  var FX={2009:46.5362,2010:44.7223,2011:53.1053,2012:54.9947,2013:61.8998,2014:63.19,2015:66.1537,2016:67.9191,2017:63.8752,2018:69.633,2019:71.3788,2020:73.067,2021:74.368,2022:82.6655,2023:83.1715,2024:85.6035,2025:89.8694};
  var range=document.getElementById('tmRange'), $=function(id){return document.getElementById(id);};
  var maxAll=0;
  for(var y=2010;y<=2021;y++){var a=y-1,b=y+4;maxAll=Math.max(maxAll,100*SPX[b]/SPX[a]*FX[b]/FX[a],100*NIFTY[b]/NIFTY[a]);}
  function inr(v){return '₹'+Math.round(v).toLocaleString('en-IN');}
  function render(){
    var y=+range.value, a=y-1, b=y+4;
    var spUsd=100*SPX[b]/SPX[a], fx=FX[b]/FX[a], sp=spUsd*fx, nf=100*NIFTY[b]/NIFTY[a];
    $('tmYear').textContent=y;
    $('tmSpan').textContent='Jan '+y+' → Dec '+b;
    $('spVal').textContent=inr(sp);
    $('nfVal').textContent=inr(nf);
    $('spSub').textContent='$100 → $'+Math.round(spUsd)+' · dollar '+(fx>=1?'+':'')+Math.round((fx-1)*100)+'% vs ₹';
    $('nfSub').textContent='₹100 → '+inr(nf);
    $('spBar').style.width=(sp/maxAll*100)+'%';
    $('nfBar').style.width=(nf/maxAll*100)+'%';
    $('spStart').style.left=$('nfStart').style.left=(100/maxAll*100)+'%';
    var d=Math.round(sp-nf);
    var w=sp>nf?'sp':'nf';if(lastW&&w!==lastW){var vv=$('verdict');vv.classList.remove('flip');void vv.offsetWidth;vv.classList.add('flip');}lastW=w;
    $('verdict').textContent=d>0?('The S&P 500 finished '+inr(d)+' ahead, in rupees.'):d<0?('The Nifty 50 finished '+inr(-d)+' ahead. Some years, India wins.'):'They finished level.';
    range.setAttribute('aria-valuetext','Invested in '+y+': S&P 500 '+inr(sp)+', Nifty 50 '+inr(nf));
  }
  range.addEventListener('input',render);
  render();
})();


/* Site behaviour: nav, CTA hand-off, reveals, count-ups, page fades, contact form */
(function(){
  var root=document.documentElement;
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Nav CTA: hidden on the home hero, appears once you scroll past it */
  var hero=document.querySelector('.hero'), navCta=document.getElementById('navCta');
  if(hero&&navCta){
    var set=function(dock){navCta.classList.toggle('tucked',!dock);navCta.tabIndex=dock?0:-1;};
    var check=function(){set(window.scrollY>hero.offsetHeight*0.55);};
    window.addEventListener('scroll',check,{passive:true}); check();
  }

  var nav=document.getElementById('nav'), btn=document.getElementById('menuBtn');
  if(btn){btn.addEventListener('click',function(){var o=nav.classList.toggle('open');btn.setAttribute('aria-expanded',o?'true':'false');btn.textContent=o?'Close':'Menu';});}

  /* Reveal hooks */
  document.querySelectorAll('.case-row,.reasons').forEach(function(el){el.classList.add('rv-line');});
  document.querySelectorAll('.slab,.post').forEach(function(el){el.classList.add('rv-line-b');});
  document.querySelectorAll('.rv-line,.rv-line-b').forEach(function(el){el.style.setProperty('--lc',el.closest('.band-paper')?'var(--line-dark)':'var(--line)');});

  /* Count-ups */
  function countUp(el){
    if(el.dataset.done) return; el.dataset.done='1';
    var node=null; for(var n=el.firstChild;n;n=n.nextSibling){if(n.nodeType===3&&/\d/.test(n.nodeValue)){node=n;break;}}
    if(!node||reduce) return;
    var orig=node.nodeValue, inr=/₹/.test(orig)&&!/L$/.test(orig.trim());
    var parts=[]; orig.replace(/\d[\d,]*(\.\d+)?/g,function(m,dec,off){parts.push({m:m,off:off,v:parseFloat(m.replace(/,/g,'')),dec:dec?dec.length-1:0,comma:m.indexOf(',')>=0});return m;});
    if(!parts.length) return;
    var t0=performance.now(), dur=1000;
    function fmt(p,v){var s=v.toFixed(p.dec);if(p.comma){s=Number(s).toLocaleString(inr?'en-IN':'en-US',{minimumFractionDigits:p.dec,maximumFractionDigits:p.dec});}return s;}
    (function step(t){
      var k=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-k,3), out='', pos=0;
      parts.forEach(function(p){out+=orig.slice(pos,p.off)+fmt(p,p.v*e);pos=p.off+p.m.length;});
      node.nodeValue=out+orig.slice(pos);
      if(k<1) requestAnimationFrame(step); else node.nodeValue=orig;
    })(t0);
  }

  var targets=document.querySelectorAll('.rv-line,.rv-line-b,.slab,.vs,.countup,.steps,.tiles,.flow,.gets');
  if('IntersectionObserver' in window&&!reduce){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');if(e.target.classList.contains('countup'))countUp(e.target);io.unobserve(e.target);}});},{rootMargin:'0px 0px -12% 0px'});
    targets.forEach(function(el){io.observe(el);});
  } else { targets.forEach(function(el){el.classList.add('in');}); }

  /* Page fades between internal pages */
  document.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('a[href]'); if(!a||reduce) return;
    var href=a.getAttribute('href');
    if(a.target||e.metaKey||e.ctrlKey||e.shiftKey||!href||href.charAt(0)==='#'||/^(https?:|mailto:|tel:)/.test(href)) return;
    e.preventDefault(); document.body.classList.add('leaving');
    setTimeout(function(){window.location.href=a.href;},160);
  });
  window.addEventListener('pageshow',function(){document.body.classList.remove('leaving');});

  /* Contact tabs: investor | partner (?type=partner opens the partner tab) */
  var tabInv=document.getElementById('tab-inv'), tabPar=document.getElementById('tab-par');
  if(tabInv&&tabPar){
    var show=function(par,focus){
      tabInv.setAttribute('aria-selected',par?'false':'true');tabPar.setAttribute('aria-selected',par?'true':'false');
      tabInv.tabIndex=par?-1:0;tabPar.tabIndex=par?0:-1;
      document.getElementById('panel-inv').hidden=par;document.getElementById('panel-par').hidden=!par;
      if(focus)(par?tabPar:tabInv).focus();
      try{var u=new URL(location.href);if(par)u.searchParams.set('type','partner');else u.searchParams.delete('type');history.replaceState(null,'',u);}catch(e){}
    };
    tabInv.addEventListener('click',function(){show(false);});
    tabPar.addEventListener('click',function(){show(true);});
    [tabInv,tabPar].forEach(function(t){t.addEventListener('keydown',function(e){if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();show(t===tabInv,true);}});});
    var qs=new URLSearchParams(location.search);
    if(qs.get('type')==='partner')show(true);
    var ref=qs.get('ref')||qs.get('utm_source')||'';
    document.querySelectorAll('.mc-form .ref').forEach(function(i){i.value=ref;});
  }

  /* Partner CTAs: track clicks; sticky bar on mobile after the hero */
  document.querySelectorAll('a[data-ev]').forEach(function(a){a.addEventListener('click',function(){if(window.gtag)gtag('event','partner_cta_click',{placement:a.dataset.ev});});});
  var sticky=document.getElementById('stickyCta'), pHero=document.querySelector('.p-hero');
  if(sticky&&pHero){
    document.body.classList.add('has-sticky');
    var onS=function(){var past=window.scrollY>pHero.offsetHeight*0.8, nearEnd=window.innerHeight+window.scrollY>document.body.scrollHeight-260;sticky.classList.toggle('show',past&&!nearEnd);};
    window.addEventListener('scroll',onS,{passive:true});onS();
  }

  /* Forms: send through Web3Forms. Investor → generate_lead, partner → partner_lead */
  var MSG={
    name:'Add your name.', email:'Enter a valid email, like name@domain.com.', phone:'Add a mobile number we can WhatsApp.',
    city:'Add your city.', type:'Tell us what you do.', aum:'Pick the assets you service.'
  };
  document.querySelectorAll('form.mc-form').forEach(function(f){
    var err=f.querySelector('.err'), kind=f.dataset.kind, partner=kind==='partner';
    f.addEventListener('submit',function(e){
      e.preventDefault();
      var bad=null;
      f.querySelectorAll('[data-req]').forEach(function(el){
        if(bad)return; var k=el.dataset.req, val=el.value.trim();
        if(k==='email'?!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val):k==='phone'?val.replace(/\D/g,'').length<10:!val)bad=el;
      });
      if(bad){err.textContent=MSG[bad.dataset.req];bad.focus();return;}
      err.textContent='';
      var data={}; Array.prototype.forEach.call(f.elements,function(el){if(el.name&&el.type!=='checkbox'&&el.type!=='submit')data[el.name]=el.value.trim();});
      var name=data.name, first=name.split(' ')[0];
      var wrap=document.getElementById(f.dataset.wrap), btn=f.querySelector('button[type=submit]'), key=f.dataset.key||'';
      function card(title,body){var d=document.createElement('div');d.className='done';d.setAttribute('role','status');var h=document.createElement('h3');h.textContent=title;var p=document.createElement('p');p.className='lede';p.textContent=body;d.append(h,p);wrap.replaceChildren(d);}
      function done(ok){
        if(ok){
          if(window.gtag)gtag('event',partner?'partner_lead':'generate_lead',{form_name:kind});
          card('Thanks, '+first+'.',partner?'One of our founders will call you within 2 working days.':'We’ll be in touch within two working days.');
        } else card('That didn’t go through.','Please email us at '+(partner?'partners@':'hello@')+'meridiancapital.in and we’ll reply within two working days.');
      }
      if(!key||key.indexOf('YOUR_')===0){card('Thanks, '+first+'.','Preview: the form isn’t connected to an inbox yet, so nothing was sent.');return;}
      btn.disabled=true;btn.textContent='Sending…';
      data.access_key=key;
      data.subject=partner?('New partner enquiry: '+name+', '+(data.city||'')+', '+(data.aum_band||'')):'New investor enquiry: '+name;
      data.from_name='Meridian Capital website';
      data.enquiry_type=kind;
      data.botcheck=f.querySelector('.bot').checked;
      fetch('https://api.web3forms.com/submit',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(data)})
        .then(function(r){return r.json();}).then(function(j){done(!!j.success);}).catch(function(){done(false);});
    });
  });
})();

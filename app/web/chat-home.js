/* One movable conversation, shared by the home and the global side panel. */
(() => {
 'use strict';
 const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const icon=n=>`<i class="ph ph-${n}" aria-hidden="true"></i>`;
 const date=v=>v?new Date(v.length===10?v+'T12:00:00+08:00':v).toLocaleDateString('en-SG',{day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Singapore'}):'Date unavailable';
 const number=v=>Number.isFinite(v)?Math.round(v).toLocaleString('en-SG'):'—';
 const safeUrl=v=>{try{const u=new URL(v);return u.protocol==='https:'?esc(u.href):'#';}catch{return '#';}};
 const scrub=t=>String(t).replace(/(?<!\d)\d{6}(?!\d)/g,'[private postal code]').replace(/\b1\.\d+\s*[, /]\s*103\.\d+\b/g,'[private coordinates]');
 const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 let data,hooks,engine,root,home,turns=[],history=[],controller=null,language='en',panelOpen=false,lastQuestion='',context='';
 const TEXT={
  en:{placeholder:'Ask about dengue, or enter a postal code…',locate:'Use my location',new:'New chat',send:'Send',stop:'Stop',example:'Try an example',chips:['Where should we check this weekend?','Will cases rise next week?','写一份中文居民通知','I have a fever, what now?']},
  zh:{placeholder:'询问骨痛热症，或输入邮政编码…',locate:'使用我的位置',new:'新对话',send:'发送',stop:'停止',example:'试用示例',chips:['周末应该先检查哪里？','下周病例会增加吗？','写一份中文居民通知','我发烧了，该怎么办？']},
  ms:{placeholder:'Tanya tentang denggi, atau masukkan poskod…',locate:'Guna lokasi saya',new:'Sembang baharu',send:'Hantar',stop:'Henti',example:'Cuba contoh',chips:['Di mana patut kami periksa hujung minggu ini?','Adakah kes akan meningkat minggu depan?','Tulis notis penduduk dalam Bahasa Melayu','Saya demam, apa perlu dibuat?']},
  ta:{placeholder:'டெங்கி பற்றி கேளுங்கள் அல்லது அஞ்சல் குறியீட்டை உள்ளிடுங்கள்…',locate:'எனது இருப்பிடம்',new:'புதிய உரையாடல்',send:'அனுப்பு',stop:'நிறுத்து',example:'எடுத்துக்காட்டு',chips:['இந்த வார இறுதியில் எங்கு ஆய்வு செய்யலாம்?','அடுத்த வாரம் பாதிப்புகள் அதிகரிக்குமா?','தமிழில் குடியிருப்பாளர் அறிவிப்பு எழுதவும்','எனக்கு காய்ச்சல், என்ன செய்வது?']}
 };
 function save(){try{sessionStorage.setItem('denguesux:conversation',JSON.stringify({turns:turns.filter(t=>!t.private).slice(-12),history:history.slice(-8),language,context}));}catch{}}
 function restore(){try{const s=JSON.parse(sessionStorage.getItem('denguesux:conversation'));if(s&&Array.isArray(s.turns)&&Array.isArray(s.history)){turns=s.turns.filter(t=>typeof t.question==='string').slice(-12);history=s.history.filter(m=>['user','assistant'].includes(m.role)&&typeof m.content==='string').slice(-8).map(m=>({...m,content:scrub(m.content)}));language=TEXT[s.language]?s.language:'en';context=scrub(s.context||'');}}catch{}}
 function greeting(){const hour=Number(new Intl.DateTimeFormat('en-SG',{hour:'numeric',hourCycle:'h23',timeZone:'Asia/Singapore'}).format(new Date()));return hour<12?'Good morning.':hour<18?'Good afternoon.':'Good evening.';}
 function sourcesHTML(sources=[]){return `<div class="ask-sources">${sources.map((s,i)=>`<span>[${i+1}] ${s.url?`<a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`:esc(s.name)} · ${date(s.date)}</span>`).join('')}</div>`;}
 function markdown(text){return esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\[\[[^\]]*\]\]/g,'').split('\n\n').map(p=>`<p>${p.replace(/\n/g,'<br>')}</p>`).join('');}
 function renderTurn(t){
  const el=document.createElement('article');el.className='conversation-turn';el.innerHTML=`<div class="chat-question">${esc(t.question)}</div><div class="chat-answer"><h2 tabindex="-1">${icon('chat-circle-text')} DengueSUX <small>${esc(t.mode||'Local, no AI')}</small></h2><div class="chat-answer-body">${t.answer?markdown(t.answer):'<p role="status">Reading the saved data…</p>'}</div></div>`;
  $('#ask-log').append(el);if(t.html)el.querySelector('.chat-answer-body').innerHTML=t.html;
  if(t.cards)window.AnswerCards?.render(el.querySelector('.chat-answer-body'),t.cards,data,language);
  if(t.sources)el.querySelector('.chat-answer-body').insertAdjacentHTML('beforeend',sourcesHTML(t.sources));
  if(t.trace?.length)el.querySelector('.chat-answer-body').insertAdjacentHTML('beforeend',`<details class="ask-trace"><summary>Sources & tool details</summary>${t.trace.map(r=>`<p>${esc(r.tool||r.name)}</p>${r.result?.sql?`<details><summary>Show Genie SQL · AI-generated</summary><pre>${esc(r.result.sql)}</pre></details>`:''}`).join('')}</details>`);
  return el;
 }
 function setConversation(){const active=turns.length>0;home?.classList.toggle('has-conversation',active);root.classList.toggle('has-conversation',active);$('#ask-log').hidden=!active;root.querySelector('.chat-new').hidden=!active;}
 function mountPanel(open){
  panelOpen=open;$('#ask-panel').hidden=!open;$('#ask-fab').setAttribute('aria-expanded',String(open));document.body.classList.toggle('ask-open',open);
  (open?$('#ask-panel .panel-chat'):$('#home-conversation')).append(root);
  const modal=open&&matchMedia('(max-width:720px)').matches;$('.app-shell').inert=modal;
  $('#ask-panel').toggleAttribute('aria-modal',modal);if(modal)$('#ask-panel').setAttribute('role','dialog');else $('#ask-panel').removeAttribute('role');
  window.AnswerCards?.resize();$('#ask-input').focus();
 }
 function syncRoute(){if(!home)return;const week=['','#week'].includes(location.hash);if(week&&panelOpen)mountPanel(false);if(!week&&!panelOpen&&root.parentElement!==$('#home-conversation'))$('#home-conversation').append(root);}
 function localQuestion(q){const t=TEXT[language],i=t.chips.indexOf(q);return i>=0?TEXT.en.chips[i]:q;}
 async function answerLocal(question){
  const q=localQuestion(question)+(context?' '+context:''),res=await engine.respond(q,()=>{});
  const box=document.createElement('div');box.innerHTML=res.answer.paragraphs.join('\n');
  return {answer:box.textContent,cards:window.AnswerCards?.fromTools(res.results,data)||[],sources:res.answer.sources,trace:res.results,mode:'Local, no AI'};
 }
 async function answerRemote(question,signal){
  if(window.DENGUESUX_DATA)return null;
  const status=await fetch('/api/chat/status',{signal}).then(r=>r.json());if(!status.enabled)return null;
  const messages=[...history,{role:'user',content:scrub(question+(context?'\nPlace context: '+context:''))}].slice(-8);
  const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({messages,language}),signal});if(!r.ok)throw Error('Assistant unavailable');return {...await r.json(),mode:'AI · dated sources'};
 }
 function finish(t,el){el.remove();const answer=renderTurn(t);setConversation();save();answer.querySelector('h2').focus({preventScroll:true});answer.scrollIntoView({block:'nearest',behavior:reduced()?'instant':'smooth'});}
 async function ask(question){
  if(controller||!question.trim())return;lastQuestion=question;
  const postal=question.match(/(?<!\d)\d{6}(?!\d)/);if(postal&&window.LocationCheck)return window.LocationCheck.lookup(postal[0],question);
  // Do not forward coordinates or a postal code in any branch, even if lookup is unavailable.
  if(postal||/\b1\.\d+\s*[, /]\s*103\.\d+\b/.test(question))return privateAnswer('Location check',{answer:'Use a six-digit postal code or “Use my location”. Precise location stays in your browser.'});
  if(window.CareActions?.handle(question))return;
  const t={question:scrub(question)},el=renderTurn(t);turns.push(t);const apply=()=>setConversation();if(document.startViewTransition&&!reduced())document.startViewTransition(apply);else apply();
  controller=new AbortController();setBusy(true);
  try{let result;try{result=await answerRemote(question,controller.signal);}catch(e){if(controller.signal.aborted)throw e;}result||=await answerLocal(question);Object.assign(t,result);history.push({role:'user',content:scrub(question)},{role:'assistant',content:scrub(t.answer||'')});history=history.slice(-8);}
  catch(e){t.answer=controller.signal.aborted?'Stopped. You can ask again when ready.':'The saved data could not answer this. Please check NEA for the latest information.';t.mode='Local, no AI';}
  finally{controller=null;setBusy(false);finish(t,el);}
 }
 function setBusy(busy){$('#chat-stop').hidden=!busy;$('.chat-send').hidden=busy;$('#chat-location').disabled=busy;root.setAttribute('aria-busy',String(busy));}
 function privateAnswer(question,result){const t={question,...result,private:true,mode:'On this device'};turns.push(t);const el=renderTurn(t);setConversation();el.querySelector('h2').focus({preventScroll:true});return el;}
 function clear(){controller?.abort();if(controller)return;turns=[];history=[];context='';$('#ask-log').replaceChildren();setConversation();save();$('#ask-input').focus();}
 function languageUI(){const t=TEXT[language];$('#ask-input').placeholder=t.placeholder;$('#chat-location').innerHTML=icon('crosshair-simple')+esc(t.locate);$('#chat-stop').textContent=t.stop;$('.chat-send').setAttribute('aria-label',t.send);$('.chat-new').innerHTML=icon('plus')+esc(t.new);$('.chat-suggestions').innerHTML=`<button class="ask-chip" data-example>${icon('house-line')}${esc(t.example)}</button>`+t.chips.map(q=>`<button class="ask-chip">${esc(q)}</button>`).join('');$('.chat-suggestions').querySelectorAll('button').forEach(b=>b.onclick=()=>b.hasAttribute('data-example')?window.LocationCheck?.example():ask(b.textContent));save();}
 function init(payload,callbacks,localEngine){data=payload;hooks=callbacks;engine=localEngine;restore();
  root=document.createElement('div');root.id='conversation';root.innerHTML=`<div class="chat-tools"><button class="text-button chat-new" type="button">New chat</button></div><div id="ask-log" class="conversation-log" role="log" aria-live="polite" aria-relevant="additions text"></div><div class="composer-wrap"><form id="ask-form" class="home-composer"><label class="sr-only" for="ask-input">Your question</label><textarea id="ask-input" rows="2" maxlength="600" autocomplete="off"></textarea><div class="composer-actions"><button type="button" id="chat-location" class="text-button"></button><label class="sr-only" for="chat-language">Answer language</label><select id="chat-language"><option value="en">EN</option><option value="zh">中文</option><option value="ms">BM</option><option value="ta">தமிழ்</option></select><span class="composer-space"></span><button type="button" id="chat-stop" class="outline-button" hidden>Stop</button><button class="solid-button chat-send" type="submit" aria-label="Send">${icon('arrow-up')}</button></div></form><p class="composer-privacy">Postal codes go directly to OneMap. Your location stays in this browser.</p><div class="chat-suggestions"></div></div>`;
  const panel=document.createElement('aside');panel.id='ask-panel';panel.className='ask-panel';panel.hidden=true;panel.setAttribute('aria-label','Ask DengueSUX');panel.innerHTML=`<header class="ask-head"><strong>Ask DengueSUX</strong><button class="icon-button" id="close-chat" aria-label="Close assistant">${icon('x')}</button></header><div class="panel-chat"></div>`;document.body.append(panel);panel.querySelector('.panel-chat').append(root);
  $('.topbar-actions').insertAdjacentHTML('beforeend',`<button id="ask-fab" class="ask-fab" aria-label="Ask DengueSUX" aria-expanded="false" aria-controls="ask-panel">${icon('chat-circle-text')}<span>Ask DengueSUX</span></button>`);
  $('#ask-fab').onclick=()=>{if(['','#week'].includes(location.hash))$('#ask-input').focus();else mountPanel(true);};$('#close-chat').onclick=()=>{mountPanel(false);$('#ask-fab').focus();};
  $('#ask-form').onsubmit=e=>{e.preventDefault();const q=$('#ask-input').value.trim();if(!controller&&q){$('#ask-input').value='';ask(q);}};
  $('#ask-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#ask-form').requestSubmit();}if(e.key==='ArrowUp'&&!e.target.value){e.preventDefault();e.target.value=lastQuestion;}};
  $('#chat-stop').onclick=()=>controller?.abort();document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(controller)controller.abort();else if(panelOpen)mountPanel(false);}});
  panel.addEventListener('keydown',e=>{if(e.key==='Tab'&&panel.hasAttribute('aria-modal')){const nodes=[...panel.querySelectorAll('button,textarea,select,a,summary')].filter(n=>!n.disabled&&n.getClientRects().length),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
  root.querySelector('.chat-new').onclick=clear;$('#chat-language').value=language;$('#chat-language').onchange=e=>{language=e.target.value;languageUI();};$('#chat-location').onclick=()=>window.LocationCheck?.locate();languageUI();turns.forEach(renderTurn);window.addEventListener('hashchange',syncRoute);
 }
 function mount(api){home=$('#week-view');home.classList.add('chat-home');home.insertAdjacentHTML('afterbegin',`<div class="home-intro"><div class="home-greeting">${greeting()}</div><h1>${api.liveForecast()?.headline?`Dengue is ${esc(api.liveForecast().headline.risk.toLowerCase())} in Singapore this week.`:'The latest dengue picture, in one place.'}</h1><p>${data.current.areas.filter(a=>a.risk==='High').length} areas need checking. A little care starts close to home.</p><div id="saved-places"></div></div><div id="home-conversation"></div>`);$('#home-conversation').append(root);setConversation();
  const grid=home.querySelector('.week-grid');grid.insertAdjacentHTML('beforeend',`<section class="week-activity"><header><h2>Recent activity</h2><span class="feed-status">Saved data</span></header><div id="activity-feed"><p>Cluster snapshot · ${date(data.current.as_of)}</p><a href="#map">View the latest clusters ${icon('arrow-up-right')}</a></div></section>`);
  window.LocationCheck?.init(data);window.CareActions?.init(data);window.ActivityFeed?.init(data,api);window.AnswerCards?.sparklines(home,data);syncRoute();
 }
 window.ChatHome={init,mount,ask,privateAnswer,scrub,get language(){return language;},get data(){return data;},get hooks(){return hooks;},setContext(v){context=scrub(v);save();},sourcesHTML,number,date,esc,icon,clear};
})();

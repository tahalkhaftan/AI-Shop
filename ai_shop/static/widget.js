/* Self-host this asset. It talks only to a same-origin application proxy. */
(() => {
  const script = document.currentScript;
  const endpoint = new URL(script?.dataset.endpoint || '/api/ai-shop/chat', location.href);
  if (endpoint.origin !== location.origin) throw new Error('AI-Shop widget requires a same-origin proxy.');
  const host = document.createElement('div'); document.body.append(host);
  const root = host.attachShadow({mode:'open'});
  const fa = (script?.dataset.language || document.documentElement.lang || '').startsWith('fa');
  const label = fa ? 'راهنمای خرید' : 'Shopping assistant';
  root.innerHTML = `<style>:host{font:14px/1.7 system-ui,sans-serif;--accent:var(--ai-shop-accent,#306750)}button,input{font:inherit}button{cursor:pointer;border:0;border-radius:12px;padding:8px 12px;background:var(--accent);color:white}.toggle{position:fixed;bottom:24px;right:24px;z-index:10000;border-radius:50%;width:52px;height:52px;font-size:22px}.toggle svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.panel{position:fixed;bottom:88px;right:16px;width:min(360px,calc(100vw - 32px));max-height:70vh;z-index:10000;background:white;color:#183427;border:1px solid #d4e3d9;border-radius:18px;box-shadow:0 12px 45px #1232;overflow:hidden}header{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee}.log{max-height:42vh;overflow:auto;padding:12px;white-space:pre-wrap}p{margin:0 0 12px}a{color:var(--accent);font-weight:bold}.user{background:#eef4ef;border-radius:12px;padding:8px}form{display:flex;gap:6px;padding:10px}input[type=text]{flex:1;min-width:0;border:1px solid #cbdcd1;border-radius:10px;padding:8px}.consent,small{display:block;padding:0 12px 10px;font-size:11px}.status{padding:0 12px}[hidden]{display:none!important}</style><button class="toggle" type="button" aria-label="${label}" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13v-2a9 9 0 0 1 18 0v2M3 13v3a2 2 0 0 0 2 2h2v-7H5a2 2 0 0 0-2 2Zm18 0v3a2 2 0 0 1-2 2h-2v-7h2a2 2 0 0 1 2 2Zm0 4c0 2-2 3-5 3h-2m0 0a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z"/></svg></button><section class="panel" role="dialog" aria-label="${label}" hidden dir="${fa?'rtl':'ltr'}"><header><strong>${label}</strong><button class="close" type="button" aria-label="Close">×</button></header><div class="log" role="log" aria-live="polite"></div><div class="status" role="status" hidden>${fa?'در حال پاسخ‌گویی…':'Writing a reply…'}</div><form><input type="text" maxlength="1000" dir="auto" required aria-label="${fa?'پیام شما':'Your message'}"><button type="submit">${fa?'ارسال':'Send'}</button></form><label class="consent"><input type="checkbox"> ${fa?'با ثبت یک نکتهٔ عمومی بدون اطلاعات شخصی برای بررسی موافقم.':'Allow a non-personal public FAQ suggestion to be saved for review.'}</label><small>${fa?'پردازش روی میزبان همین سایت انجام می‌شود.':'Processed on this site’s configured host.'}</small></section>`;
  const panel=root.querySelector('.panel'),log=root.querySelector('.log'),input=root.querySelector('input[type=text]'),form=root.querySelector('form'),status=root.querySelector('.status'),toggle=root.querySelector('.toggle'),send=form.querySelector('button');
  let history=[],pending=false;
  function row(text,who){const p=document.createElement('p');p.dir='auto';p.className=who||'';p.textContent=text;log.append(p);log.scrollTop=log.scrollHeight;return p;}
  row(fa?'سلام، امروز چه کمکی می‌تونم بهتون بکنم؟':'Hello! What can I help you find today?');
  function close(){panel.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus();}
  toggle.addEventListener('click',()=>{panel.hidden=!panel.hidden;toggle.setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)input.focus();});
  root.querySelector('.close').addEventListener('click',close);
  panel.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
  form.addEventListener('submit',async event=>{
    event.preventDefault();const q=input.value.trim();if(pending||!q)return;
    row(q,'user');input.value='';pending=true;send.disabled=true;status.hidden=false;
    try{
      const response=await fetch(endpoint.href,{method:'POST',headers:{'Content-Type':'application/json','X-AI-Shop-Client':'1'},credentials:'same-origin',body:JSON.stringify({message:q,history,learning_consent:root.querySelector('input[type=checkbox]').checked})});
      const result=await response.json();if(!response.ok)throw Error('unavailable');
      const p=row('');
      for(const part of result.parts||[{type:'text',text:result.reply}]){
        if(part.type==='product'||part.type==='page'){
          const url=new URL(part.url,location.href);if(url.origin!==location.origin)continue;
          const a=document.createElement('a');a.href=url.href;a.textContent=part.text;p.append(a);
        }else if(part.type==='price'){
          p.append(document.createTextNode(new Intl.NumberFormat(fa?'fa-IR':undefined,{minimumFractionDigits:part.decimals,maximumFractionDigits:part.decimals}).format(part.amount_minor/10**part.decimals)+' '+result.labels.currency_label));
        }else p.append(document.createTextNode(part.text||''));
      }
      if(result.learning?.saved)row(fa?'پیشنهاد عمومی برای بررسی ثبت شد.':'A public FAQ suggestion was saved for review.');
      history=[...history,{role:'user',content:q},{role:'assistant',content:String(result.reply).slice(0,1400)}].slice(-12);
    }catch{row(fa?'پاسخ دریافت نشد؛ کمی بعد دوباره تلاش کنید.':'The assistant is unavailable. Please try again shortly.');if(!input.value)input.value=q;}
    finally{pending=false;send.disabled=false;status.hidden=true;if(!panel.hidden)input.focus();}
  });
})();

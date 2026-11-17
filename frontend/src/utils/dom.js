export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const fmt=v=>typeof v==='number'?new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(v):String(v??'—');
export const date=v=>new Date(v*1000).toLocaleString('zh-CN',{hour12:false});
export function notify(message,error=false){const t=document.querySelector('#toast');t.textContent=message;t.className=error?'show error':'show';setTimeout(()=>t.className='',5000);}
const pad=n=>String(n).padStart(2,'0');
export function toLocalInput(epochSeconds){
 if(!epochSeconds)return '';
 const d=new Date(epochSeconds*1000);
 return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes());
}
export function fromLocalInput(value){
 if(!value)return null;
 const t=Date.parse(value);
 return Number.isFinite(t)?t/1000:null;
}

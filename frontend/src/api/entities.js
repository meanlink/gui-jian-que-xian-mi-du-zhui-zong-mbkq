import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const closure={
 bands:jobId=>api('/closure/bands?job_id='+jobId),
 orders:()=>api('/closure/orders'),
 order:id=>api('/closure/orders/'+id),
 createOrder:data=>api('/closure/orders',{method:'POST',body:JSON.stringify(data)}),
 registerRetest:data=>api('/closure/retests',{method:'POST',body:JSON.stringify(data)}),
 rework:(id,reason)=>api('/closure/orders/'+id+'/rework',{method:'POST',body:JSON.stringify({reason})}),
 stats:()=>api('/closure/stats'),
};

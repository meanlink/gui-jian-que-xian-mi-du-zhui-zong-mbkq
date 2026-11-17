/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,job_id:number,band_key:string,title:string,from_km:number,to_km:number,neighborhood_m:number,coverage_from_km:number,coverage_to_km:number,params:Object,completed_at:number,status:string,current_period:number,closed_at:?number,closure_retest_id:?number}} ClosureOrder */
/** @typedef {{id:number,order_id:number,period_no:number,status:string,reason:string,opened_at:number,closed_at:?number}} AcceptancePeriod */
/** @typedef {{id:number,order_id:number,period_id:number,period_no:number,dataset_id:number,collected_at:number,coverage_from_km:number,coverage_to_km:number,result:string,time_ok:boolean,coverage_ok:boolean,core_points_in_band:number,high_isolated_in_band:number,findings:Object,reject_reasons:string[],note:string}} Retest */
export {};

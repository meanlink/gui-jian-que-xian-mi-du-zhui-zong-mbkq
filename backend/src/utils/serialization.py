import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def closure_order_dict(o):
    return {k:getattr(o,k) for k in ['id','job_id','band_key','title','from_km','to_km','neighborhood_m',
            'coverage_from_km','coverage_to_km','params','high_severity_threshold','completed_at','status',
            'current_period','closed_at','closure_retest_id','created_by','created_at']}
def period_dict(p):
    return {k:getattr(p,k) for k in ['id','order_id','period_no','status','reason','opened_at','closed_at']}
def retest_dict(r):
    return {k:getattr(r,k) for k in ['id','order_id','period_id','period_no','dataset_id','collected_at',
            'coverage_from_km','coverage_to_km','dataset_checksum','result','time_ok','coverage_ok',
            'core_points_in_band','high_isolated_in_band','findings','reject_reasons','registered_by',
            'registered_at','note']}

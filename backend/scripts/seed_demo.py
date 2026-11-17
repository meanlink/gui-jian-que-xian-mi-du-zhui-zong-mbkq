import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, ClosureOrder, AcceptancePeriod, Retest
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import closure as closure_service
from src.schemas.closure import ClosureOrderInput, RetestInput, ReworkInput
from src.utils.security import hash_password
from src.utils.serialization import checksum


def retest_seed_records():
    """模拟检修后复测：
    - 12.4km 缺陷带已整治，带内零缺陷（零缺陷也有覆盖凭据）；
    - 48.2km 一带仅抽除约20%点，密度核心仍成立，复测不通过；
    - 93.7km 一带抽疏到只剩少量点，保留等级≥4的高等级孤立点。
    返回 (记录, 固定覆盖范围 起点km, 终点km)。
    """
    base = seed_records()
    rows = []
    kept_high_in_third = 0
    for idx, row in enumerate(base):
        m = row["mileage_km"]
        if 11.6 <= m <= 13.2:
            continue  # 第一条缺陷带整体消除，形成零缺陷场景
        if 47.4 <= m <= 49.0 and idx % 8 == 0:
            continue  # 第二条带仅抽除约1/8，密度核心依旧，用于演示复测拒绝
        if 93.2 <= m <= 94.2:
            if row["severity"] < 4 or kept_high_in_third >= 3:
                continue  # 第三条带抽疏，只留3个高等级点作为高等级孤立点
            kept_high_in_third += 1
        rows.append(dict(row))
    # 保证复测批次仍满足最少 10 点的算法口径（补回分散点，不落在三个缺陷带内）
    if len(rows) < 12:
        for r in base:
            if not any(lo <= r["mileage_km"] <= hi for lo, hi in [(11.6, 13.2), (47.4, 49.0), (93.2, 94.2)]):
                rows.append(dict(r))
                if len(rows) >= 12:
                    break
    rows = sorted(rows, key=lambda r: r["mileage_km"])
    coverage_from = min(r["mileage_km"] for r in base) - 0.5
    coverage_to = max(r["mileage_km"] for r in base) + 0.5
    return rows, coverage_from, coverage_to


def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        # —— 销项验收演示数据（幂等）——
        _seed_closure_demo(db, m)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,ClosureOrder,AcceptancePeriod,Retest]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts


def _seed_closure_demo(db, m):
    job = db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name']))
    admin = db.scalar(select(User).where(User.role=='admin'))
    band_rows = [r for r in job.result['table']['rows'] if str(r['band']).startswith('缺陷带')]
    if not band_rows or db.scalar(select(func.count()).select_from(ClosureOrder)):
        return
    retest_rows, coverage_from, coverage_to = retest_seed_records()
    retest_ds = Dataset(name='检修后复测批次 · 南环上行', source='rail-density-retest-202611.csv',
                        records=retest_rows, checksum=checksum(retest_rows), created_at=time.time()-1800)
    db.add(retest_ds); db.flush()
    now = time.time()

    def retest_input(order, note):
        return RetestInput(order_id=order.id, dataset_id=retest_ds.id, collected_at=now - 3600,
                           coverage_from_km=coverage_from, coverage_to_km=coverage_to, note=note)

    # 销项单1：已整治缺陷带，完工后复测、覆盖完整、重算无核心点/高等级孤立点（带内零缺陷）→ 已销项
    o1, _ = closure_service.create_order(db, ClosureOrderInput(
        job_id=job.id, band_key=band_rows[0]['band'], neighborhood_m=100.0,
        completed_at=now - 7200), admin)
    closure_service.register_retest(db, retest_input(o1, 'seed：整治后首次复测，覆盖原带及两侧100米邻域，带内零缺陷'), admin)
    db.add(Audit(actor='seed', action='demo.closure_pass', detail={'order': o1.id}, at=now))
    # 销项单2：残留密度核心，复测被拒绝；随后返工开启第2验收期，旧期证据保留
    o2, _ = closure_service.create_order(db, ClosureOrderInput(
        job_id=job.id, band_key=band_rows[1]['band'], neighborhood_m=100.0,
        completed_at=now - 7200), admin)
    closure_service.register_retest(db, retest_input(o2, 'seed：复测仍检出密度核心，不予销项'), admin)
    closure_service.rework(db, o2.id, admin, 'seed：补修后重新验收')
    db.add(Audit(actor='seed', action='demo.closure_rework', detail={'order': o2.id}, at=now))
    # 销项单3：抽疏后残留高等级孤立点，复测被拒绝，跟踪中
    if len(band_rows) >= 3:
        o3, _ = closure_service.create_order(db, ClosureOrderInput(
            job_id=job.id, band_key=band_rows[2]['band'], neighborhood_m=100.0,
            completed_at=now - 7200), admin)
        closure_service.register_retest(db, retest_input(o3, 'seed：带内仍有高等级孤立点，不予销项'), admin)
        db.add(Audit(actor='seed', action='demo.closure_reject', detail={'order': o3.id}, at=now))


if __name__=='__main__':seed()

"""缺陷带销项与复测验收领域服务。

规则口径（与 BUSINESS 文档一致）：
1. 销项单只能从已批准试验的缺陷带建立，范围、DBSCAN 参数、完工时间在建立时固定。
2. 复测必须登记采集时间与覆盖范围；采集晚于完工、且覆盖原带及两侧邻域才有验收资格，
   零缺陷复测同样保留覆盖凭据。
3. 按销项单固定参数对复测批次重算：原带内仍存在核心点、或高等级孤立（噪声）点，则不销项。
4. 返工开启新验收期；旧期复测证据保留但不参与新期判定。
5. 复测结论与销项状态在同一事务内一次性生效；中断后重复登记（同批次同期）幂等，
   不新增结论；返工与验收并发时，旧期结果拒绝写入新期。
"""
import time
from fastapi import HTTPException
from sqlalchemy import select

from src.models import Job, Dataset, ClosureOrder, AcceptancePeriod, Retest
from src.services.business import run_clustering

KM_TOL = 1e-9
DEFAULT_NEIGHBORHOOD_M = 100.0


def _band_rows(job):
    return [r for r in (job.result or {}).get("table", {}).get("rows", []) if str(r.get("band", "")).startswith("缺陷带")]


def list_bands(db, job_id):
    """供前端建立销项单：仅已批准完成试验的密集缺陷带可选择（噪声分组不可建单）。"""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "分析任务不存在")
    if job.status != "completed" or not job.approved:
        raise HTTPException(409, "仅已完成且获批准的试验缺陷带可以建立销项单")
    return _band_rows(job)


def create_order(db, data, user):
    job = db.get(Job, data.job_id)
    if not job:
        raise HTTPException(404, "分析任务不存在")
    if job.status != "completed" or not job.approved:
        raise HTTPException(409, "仅已完成且获批准的试验缺陷带可以建立销项单")
    band = next((r for r in _band_rows(job) if r.get("band") == data.band_key), None)
    if not band:
        raise HTTPException(404, "该试验结果中不存在指定缺陷带，或其为孤立/稀疏点分组（不可建单）")
    try:
        from_km = float(band["from_km"])
        to_km = float(band["to_km"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "缺陷带里程范围缺失或无效") from exc
    if to_km <= from_km:
        raise HTTPException(422, "缺陷带终点里程必须大于起点里程")
    neighborhood_m = data.neighborhood_m
    if not (0 < neighborhood_m <= 5000):
        raise HTTPException(422, "两侧邻域宽度须在 0~5000 米之间")
    completed_at = data.completed_at
    if completed_at is None:
        completed_at = time.time()
    if not isinstance(completed_at, (int, float)) or completed_at <= 0:
        raise HTTPException(422, "完工时间须为有效的时间戳（秒）")
    if completed_at > time.time() + 86400:
        raise HTTPException(422, "完工时间不能晚于当前时间一天以上")
    neighborhood_km = neighborhood_m / 1000.0
    # 固定快照：参数直接取试验参数，不接受调用方覆盖
    order = ClosureOrder(
        job_id=job.id, band_key=data.band_key,
        title=data.title or f"{job.name} · {data.band_key} 销项单",
        from_km=from_km, to_km=to_km, neighborhood_m=neighborhood_m,
        coverage_from_km=round(from_km - neighborhood_km, 6),
        coverage_to_km=round(to_km + neighborhood_km, 6),
        params=dict(job.params), high_severity_threshold=4,
        completed_at=float(completed_at), status="open", current_period=1,
        created_by=user.id, created_at=time.time(),
    )
    db.add(order)
    db.flush()
    period = AcceptancePeriod(order_id=order.id, period_no=1, status="active",
                              reason="初始验收期", opened_at=time.time())
    db.add(period)
    db.flush()
    return order, period


def _evaluate(db, order, period, dataset, collected_at, coverage_from_km, coverage_to_km):
    """按固定参数重算复测批次并给出验收结论；纯计算，不写库。"""
    reasons = []
    # 第1期只须晚于完工；返工后的新期还须晚于该期开启时间，
    # 使返工前采集的旧数据即使并发写入也无法充当新期证据。
    if period.period_no <= 1:
        time_threshold = order.completed_at
        threshold_label = "检修完工时间"
    else:
        time_threshold = max(order.completed_at, period.opened_at)
        threshold_label = f"第{period.period_no}验收期开启（返工）时间"
    time_ok = collected_at > time_threshold
    if not time_ok:
        reasons.append(f"复测采集时间不晚于{threshold_label}，不具备该验收期资格")
    coverage_ok = (coverage_from_km <= order.coverage_from_km + KM_TOL
                   and coverage_to_km >= order.coverage_to_km - KM_TOL
                   and coverage_to_km > coverage_from_km)
    if not coverage_ok:
        reasons.append(
            f"复测覆盖 {coverage_from_km:.4f}~{coverage_to_km:.4f}km 未完整覆盖原带及两侧邻域 "
            f"{order.coverage_from_km:.4f}~{order.coverage_to_km:.4f}km")
    try:
        clustered = run_clustering(dataset.records, order.params)
    except ValueError as exc:
        # 复测数据不满足算法口径：登记为被拒绝的凭据，而不是让请求失败
        reasons.append(f"复测批次无法按固定参数重算：{exc}")
        return {"result": "rejected", "time_ok": time_ok, "coverage_ok": coverage_ok,
                "core_points_in_band": 0, "high_isolated_in_band": 0,
                "reject_reasons": reasons,
                "findings": {"note": str(exc), "in_band_records": 0, "zero_defect": False}}
    mileage = clustered["mileage"]
    severity = clustered["severity"]
    labels = clustered["labels"]
    core_mask = clustered["core_mask"]
    in_band = (mileage >= order.from_km - KM_TOL) & (mileage <= order.to_km + KM_TOL)
    core_in_band = in_band & core_mask
    high_noise_in_band = in_band & (labels == -1) & (severity >= order.high_severity_threshold)
    core_count = int(core_in_band.sum())
    high_count = int(high_noise_in_band.sum())
    if core_count:
        reasons.append(f"按原参数重算，原带内仍有 {core_count} 个核心点（密度条件依旧成立），不予销项")
    if high_count:
        reasons.append(f"原带内仍有 {high_count} 个等级≥{order.high_severity_threshold} 的高等级孤立点，不予销项")
    zero_defect = int(in_band.sum()) == 0
    findings = {
        "in_band_records": int(in_band.sum()),
        "zero_defect": zero_defect,
        "core_point_ids": [clustered["records"][i].get("defect_id", f"#{i}") for i in range(len(in_band)) if core_in_band[i]],
        "high_isolated_ids": [clustered["records"][i].get("defect_id", f"#{i}") for i in range(len(in_band)) if high_noise_in_band[i]],
        "coverage_credential": {
            "required_from_km": order.coverage_from_km, "required_to_km": order.coverage_to_km,
            "actual_from_km": coverage_from_km, "actual_to_km": coverage_to_km,
            "covered": coverage_ok,
        },
        "time_credential": {"completed_at": order.completed_at,
                            "period_opened_at": period.opened_at,
                            "required_after": time_threshold,
                            "threshold_label": threshold_label,
                            "collected_at": collected_at, "after_completion": time_ok},
        "recomputed_params": dict(order.params),
    }
    if zero_defect:
        findings["zero_defect_note"] = "原带内零缺陷；覆盖凭据仍完整登记，可作为验收依据。"
    accepted = time_ok and coverage_ok and not core_count and not high_count
    return {"result": "passed" if accepted else "rejected", "time_ok": time_ok,
            "coverage_ok": coverage_ok, "core_points_in_band": core_count,
            "high_isolated_in_band": high_count, "reject_reasons": reasons, "findings": findings}


def register_retest(db, data, user):
    # 行级锁定销项单，保证“验收与返工并发”时两者串行化
    order = db.scalar(select(ClosureOrder).where(ClosureOrder.id == data.order_id).with_for_update())
    if not order:
        raise HTTPException(404, "销项单不存在")
    dataset = db.get(Dataset, data.dataset_id)
    if not dataset:
        raise HTTPException(404, "复测数据批次不存在")
    # 中断恢复优先：即使当期已验收封期，同期同批次的重复登记也返回既有结论，
    # 不新增记录、不改结论（重试不新增结论）。
    existing = db.scalar(select(Retest).where(
        Retest.order_id == order.id, Retest.period_no == order.current_period,
        Retest.dataset_id == dataset.id))
    if existing:
        period = db.get(AcceptancePeriod, existing.period_id)
        return order, period, existing, True
    period = db.scalar(select(AcceptancePeriod).where(
        AcceptancePeriod.order_id == order.id,
        AcceptancePeriod.period_no == order.current_period).with_for_update())
    if not period or period.status != "active":
        raise HTTPException(409, "当前没有可登记复测的活动验收期；如需继续请先登记返工开启新验收期")
    try:
        collected_at = float(data.collected_at)
        coverage_from_km = float(data.coverage_from_km)
        coverage_to_km = float(data.coverage_to_km)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "采集时间与覆盖里程必须是数值") from exc
    if collected_at <= 0:
        raise HTTPException(422, "采集时间须为有效的时间戳（秒）")
    if coverage_to_km <= coverage_from_km:
        raise HTTPException(422, "覆盖终点里程必须大于起点里程")

    verdict = _evaluate(db, order, period, dataset, collected_at, coverage_from_km, coverage_to_km)
    retest = Retest(
        order_id=order.id, period_id=period.id, period_no=period.period_no,
        dataset_id=dataset.id, collected_at=collected_at,
        coverage_from_km=coverage_from_km, coverage_to_km=coverage_to_km,
        dataset_checksum=dataset.checksum, result=verdict["result"],
        time_ok=verdict["time_ok"], coverage_ok=verdict["coverage_ok"],
        core_points_in_band=verdict["core_points_in_band"],
        high_isolated_in_band=verdict["high_isolated_in_band"],
        findings=verdict["findings"], reject_reasons=verdict["reject_reasons"],
        registered_by=user.id, registered_at=time.time(),
        note=(data.note or "")[:2000],
    )
    db.add(retest)
    db.flush()

    # 结论与销项状态同一事务生效：仅活动当期的通过证据可以销项
    if verdict["result"] == "passed":
        order.status = "closed"
        order.closed_at = time.time()
        order.closure_retest_id = retest.id
        period.status = "accepted"
        period.closed_at = order.closed_at
    return order, period, retest, False


def rework(db, order_id, user, reason):
    order = db.scalar(select(ClosureOrder).where(ClosureOrder.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, "销项单不存在")
    # 旧期（含已通过的一期）整体封存：证据保留，状态改为 superseded，不参与新期
    old_periods = list(db.scalars(select(AcceptancePeriod).where(
        AcceptancePeriod.order_id == order.id).with_for_update()))
    now = time.time()
    for p in old_periods:
        if p.status == "active":
            p.status = "superseded"
            p.closed_at = now
        elif p.status == "accepted":
            # 已销项后再次返工：撤销销项，原验收期同样保留但不再有效
            p.status = "superseded"
            p.closed_at = p.closed_at or now
    new_no = order.current_period + 1
    period = AcceptancePeriod(order_id=order.id, period_no=new_no, status="active",
                              reason=(reason or "返工后重新验收")[:300], opened_at=now)
    db.add(period)
    order.current_period = new_no
    order.status = "open"
    order.closed_at = None
    order.closure_retest_id = None
    db.flush()
    return order, period


def order_detail(db, order_id):
    order = db.get(ClosureOrder, order_id)
    if not order:
        raise HTTPException(404, "销项单不存在")
    periods = list(db.scalars(select(AcceptancePeriod).where(
        AcceptancePeriod.order_id == order_id).order_by(AcceptancePeriod.period_no)))
    retests = list(db.scalars(select(Retest).where(
        Retest.order_id == order_id).order_by(Retest.id)))
    return order, periods, retests

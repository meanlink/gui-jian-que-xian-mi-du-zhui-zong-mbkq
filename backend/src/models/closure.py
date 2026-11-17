from sqlalchemy import String, JSON, Double, Integer, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class ClosureOrder(Base):
    """缺陷带销项单：范围与参数在创建时固定，后续复测只能引用不能修改。"""
    __tablename__ = 'closure_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    band_key: Mapped[str] = mapped_column(String(60))          # 原试验结果中的分组键，如 缺陷带1
    title: Mapped[str] = mapped_column(String(160))
    # —— 以下为创建时固定的验收基线 ——
    from_km: Mapped[float] = mapped_column(Double)             # 原带起点
    to_km: Mapped[float] = mapped_column(Double)               # 原带终点
    neighborhood_m: Mapped[float] = mapped_column(Double)      # 两侧邻域宽度（米）
    coverage_from_km: Mapped[float] = mapped_column(Double)    # 复测必须覆盖的左边界 = 起点 - 邻域
    coverage_to_km: Mapped[float] = mapped_column(Double)      # 复测必须覆盖的右边界 = 终点 + 邻域
    params: Mapped[dict] = mapped_column(JSON, default=dict)   # 固定的 DBSCAN 参数快照
    high_severity_threshold: Mapped[int] = mapped_column(Integer, default=4)
    completed_at: Mapped[float] = mapped_column(Double)        # 检修完工时间（固定）
    status: Mapped[str] = mapped_column(String(20), default='open')
    current_period: Mapped[int] = mapped_column(Integer, default=1)
    closed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    closure_retest_id: Mapped[int | None] = mapped_column(ForeignKey('retests.id'), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)


class AcceptancePeriod(Base):
    """验收期：返工一次即开启新期；旧期证据保留但不用于新期结论。"""
    __tablename__ = 'acceptance_periods'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('closure_orders.id'))
    period_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='active')  # active/superseded/accepted
    reason: Mapped[str] = mapped_column(String(300), default='')       # 返工原因（首期为初始验收）
    opened_at: Mapped[float] = mapped_column(Double)
    closed_at: Mapped[float | None] = mapped_column(Double, nullable=True)


class Retest(Base):
    """复测登记：采集时间与覆盖范围为验收凭据，结论登记时一次性计算且不可变。"""
    __tablename__ = 'retests'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('closure_orders.id'))
    period_id: Mapped[int] = mapped_column(ForeignKey('acceptance_periods.id'))
    period_no: Mapped[int] = mapped_column(Integer)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    collected_at: Mapped[float] = mapped_column(Double)       # 现场采集时间
    coverage_from_km: Mapped[float] = mapped_column(Double)   # 本次复测实际覆盖范围
    coverage_to_km: Mapped[float] = mapped_column(Double)
    dataset_checksum: Mapped[str] = mapped_column(String(64))
    # —— 验收判定结果（登记时落库，不随状态变化重算）——
    result: Mapped[str] = mapped_column(String(20))           # passed/rejected
    time_ok: Mapped[bool] = mapped_column(Boolean)
    coverage_ok: Mapped[bool] = mapped_column(Boolean)
    core_points_in_band: Mapped[int] = mapped_column(Integer, default=0)
    high_isolated_in_band: Mapped[int] = mapped_column(Integer, default=0)
    findings: Mapped[dict] = mapped_column(JSON, default=dict)  # 判定依据明细（含零缺陷覆盖凭据）
    reject_reasons: Mapped[list] = mapped_column(JSON, default=list)
    registered_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    registered_at: Mapped[float] = mapped_column(Double)
    note: Mapped[str] = mapped_column(Text, default='')

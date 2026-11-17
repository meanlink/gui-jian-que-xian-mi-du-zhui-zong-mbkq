from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class ClosureStatus(str, Enum):
    open = 'open'          # 跟踪中，等待当期复测验收
    closed = 'closed'      # 已销项，原缺陷带通过验收
class PeriodStatus(str, Enum):
    active = 'active'      # 当前验收期，可登记复测
    superseded = 'superseded'  # 被返工开启的新期取代，证据保留但不再用于验收
    accepted = 'accepted'  # 该期复测通过并完成销项
class RetestResult(str, Enum):
    passed = 'passed'
    rejected = 'rejected'

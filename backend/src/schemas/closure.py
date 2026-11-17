from pydantic import BaseModel, Field


class ClosureOrderInput(BaseModel):
    job_id: int
    band_key: str = Field(min_length=1, max_length=60)
    title: str = Field(default="", max_length=160)
    neighborhood_m: float = Field(default=100.0, gt=0, le=5000)
    completed_at: float | None = Field(default=None, gt=0)


class RetestInput(BaseModel):
    order_id: int
    dataset_id: int
    collected_at: float = Field(gt=0)
    coverage_from_km: float
    coverage_to_km: float
    note: str = Field(default="", max_length=2000)


class ReworkInput(BaseModel):
    reason: str = Field(default="", max_length=300)

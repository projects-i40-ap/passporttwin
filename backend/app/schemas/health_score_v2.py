import math
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LifecycleHealthWeights(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    calibration_status: float = Field(default=.3, ge=0, le=1, allow_inf_nan=False)
    predicted_risk: float = Field(default=.3, ge=0, le=1, allow_inf_nan=False)
    recent_incidents: float = Field(default=.2, ge=0, le=1, allow_inf_nan=False)
    data_quality: float = Field(default=.2, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def total(self):
        if not math.isclose(sum(self.model_dump().values()),1,abs_tol=1e-9):
            raise ValueError('Lifecycle Health Score weights must sum to 1')
        return self

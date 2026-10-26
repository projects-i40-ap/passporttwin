"""Validated design weights for the explainable MVP Health Score."""

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthScoreWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_90_days: float = Field(default=0.40, ge=0, le=1, allow_inf_nan=False)
    current_error: float = Field(default=0.35, ge=0, le=1, allow_inf_nan=False)
    out_of_tolerance: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_total(self):
        if not math.isclose(sum(self.model_dump().values()), 1.0, abs_tol=1e-9):
            raise ValueError("Health Score weights must sum to 1")
        return self

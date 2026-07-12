"""DTOs for the what-if scenario API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.whatif.models import WhatIfScenario


class SynthesisViewDTO(BaseModel):
    synthesis_status: str
    conviction_score: float
    risk_penalty: float
    quant_support: str
    conflict_status: str
    dominant_concern: str | None
    note: str


class WhatIfResultDTO(BaseModel):
    scenario_label: str
    baseline: SynthesisViewDTO
    projected: SynthesisViewDTO
    status_changed: bool
    conviction_delta: float


class ScenarioPreset(BaseModel):
    id: str
    label: str
    description: str
    scenario: WhatIfScenario


class ScenarioPresetsResponse(BaseModel):
    presets: list[ScenarioPreset]


class ScenarioRunRequest(BaseModel):
    preset_id: str | None = Field(default=None, description="Built-in preset ID")
    scenario: WhatIfScenario | None = Field(default=None, description="Custom scenario")


class ScenarioRunResponse(BaseModel):
    result: WhatIfResultDTO
    baseline_regime: str
    baseline_confidence: float = Field(ge=0.0, le=1.0)

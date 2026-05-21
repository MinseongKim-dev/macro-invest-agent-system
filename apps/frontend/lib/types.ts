/**
 * TypeScript interfaces matching the FastAPI Pydantic DTOs exactly.
 * Source of truth: apps/api/dto/
 */

// ── Trust ──────────────────────────────────────────────────────────────────

export interface SourceAttribution {
  source_id: string
  source_label: string
  retrieval_timestamp: string | null
}

export interface TrustMetadata {
  snapshot_timestamp: string | null
  previous_snapshot_timestamp: string | null
  freshness_status: 'fresh' | 'stale' | 'unknown'
  availability: 'full' | 'partial' | 'degraded' | 'unavailable'
  is_degraded: boolean
  sources: SourceAttribution[]
  changed_indicators_count: number | null
  degraded_reason: string | null
}

// ── Regime ─────────────────────────────────────────────────────────────────

export interface RegimeTransitionDTO {
  transition_from_prior: string | null
  transition_type: string
  changed: boolean
}

export interface RegimeLatestResponse {
  as_of_date: string
  regime_id: string
  regime_timestamp: string
  regime_label: string
  regime_family: string
  confidence: string
  freshness_status: string
  degraded_status: string
  missing_inputs: string[]
  supporting_snapshot_id: string
  supporting_states: Record<string, string>
  transition: RegimeTransitionDTO
  rationale_summary: string
  warnings: string[]
  status: 'success' | 'degraded' | 'stale' | 'bootstrap'
  is_seeded: boolean
  data_source: string
}

export interface RegimeDeltaDTO {
  is_initial: boolean
  label_changed: boolean
  family_changed: boolean
  confidence_changed: boolean
  confidence_direction: string
  severity: string
  changed_dimensions: string[]
  prior_label: string | null
  prior_family: string | null
  prior_confidence: string | null
  label_transition: string | null
  confidence_transition: string | null
  is_regime_transition: boolean
  notable_flags: string[]
  severity_rationale: string
}

export interface RegimeCompareResponse {
  as_of_date: string
  baseline_available: boolean
  current_regime_label: string
  prior_regime_label: string | null
  transition_type: string
  changed: boolean
  current_confidence: string
  prior_confidence: string | null
  current_rationale_summary: string
  warnings: string[]
  is_seeded: boolean
  delta: RegimeDeltaDTO | null
}

// ── Signals ────────────────────────────────────────────────────────────────

export type SignalType = 'buy' | 'sell' | 'hold' | 'neutral'
export type ConflictStatus = 'clean' | 'tension' | 'mixed' | 'low_conviction'

export interface SignalSummaryDTO {
  signal_id: string
  signal_type: SignalType
  strength: string
  score: number
  trend: string
  rationale: string
  triggered_at: string
  rule_results: Record<string, boolean>
  rules_passed: number
  rules_total: number
  asset_class: string
  supporting_regime: string
  supporting_drivers: string[]
  conflicting_drivers: string[]
  is_degraded: boolean
  caveat: string | null
  conflict_status: ConflictStatus
  is_mixed: boolean
  conflict_note: string | null
  quant_support_level: string
}

export interface SignalsLatestResponse {
  country: string
  run_id: string
  signals: SignalSummaryDTO[]
  signals_count: number
  buy_count: number
  sell_count: number
  hold_count: number
  strongest_signal_id: string | null
  trust: TrustMetadata
  regime_label: string | null
  as_of_date: string | null
  is_regime_grounded: boolean
  status: 'success' | 'degraded' | 'fallback' | 'empty'
}

// ── Events ─────────────────────────────────────────────────────────────────

export interface ExternalEventDTO {
  event_id: string
  event_type: string
  title: string
  summary: string | null
  entity: string | null
  region: string | null
  market_scope: string[]
  occurred_at: string
  published_at: string | null
  ingested_at: string
  source: string
  source_url: string | null
  provider: string | null
  freshness: string
  provenance: string
  reliability_tier: string
  tags: string[]
  affected_domains: string[]
  status: string
  raw_payload_ref: string | null
  metadata: Record<string, string>
}

export interface EventsRecentResponse {
  events: ExternalEventDTO[]
  total: number
  limit_applied: number
}

// ── Alerts ─────────────────────────────────────────────────────────────────

export type AlertSeverity = 'info' | 'warning' | 'critical'

export interface AlertEventDTO {
  alert_id: string
  triggered_at: string
  trigger_type: string
  severity: AlertSeverity
  source_regime: string | null
  target_regime: string | null
  indicator_type: string | null
  context_snapshot_id: string | null
  country: string | null
  rule_id: string
  rule_name: string
  message: string
  acknowledgement_state: string
  acknowledged_at: string | null
  snoozed_until: string | null
  metadata: Record<string, string>
}

export interface AlertsRecentResponse {
  alerts: AlertEventDTO[]
  total: number
  limit_applied: number
}

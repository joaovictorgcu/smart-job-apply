/**
 * Hand-written mirrors of the backend Pydantic schemas.
 *
 * Source of truth: backend/app/schemas/*.py, backend/app/models/enums.py and
 * backend/app/ai/schemas.py. Field names must match byte-for-byte.
 */

/* -------------------------------------------------------------------------- */
/* Enums (StrEnum on the backend -> string unions here)                        */
/* -------------------------------------------------------------------------- */

export type JobStatus =
  | "discovered"
  | "analyzed"
  | "skipped"
  | "queued"
  | "applied"
  | "failed";

export type ApplicationStatus =
  | "draft"
  | "preparing"
  | "awaiting_review"
  | "submitting"
  | "submitted"
  | "discarded"
  | "failed";

/** Real-world result after an application was submitted (the pipeline board). */
export type ApplicationOutcome =
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "ghosted";

export type ApplicationEventType =
  | "job_found"
  | "job_analyzed"
  | "score_assigned"
  | "cover_letter_generated"
  | "form_opened"
  | "form_step_completed"
  | "question_answered"
  | "resume_uploaded"
  | "awaiting_review"
  | "user_edited"
  | "user_approved"
  | "submitted"
  | "outcome_changed"
  | "discarded"
  | "error";

export type AutomationRunStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "stopped"
  | "failed"
  | "blocked";

export type AutomationRunKind = "search" | "prepare" | "submit";

export type AnalysisKind = "scoring" | "cover_letter" | "screening";

export type AnswerConfidence = "high" | "medium" | "low";

export type QuestionType =
  | "text"
  | "textarea"
  | "number"
  | "select"
  | "radio"
  | "checkbox"
  | "unknown";

export const JOB_STATUSES: readonly JobStatus[] = [
  "discovered",
  "analyzed",
  "skipped",
  "queued",
  "applied",
  "failed",
];

export const APPLICATION_STATUSES: readonly ApplicationStatus[] = [
  "draft",
  "preparing",
  "awaiting_review",
  "submitting",
  "submitted",
  "discarded",
  "failed",
];

/* -------------------------------------------------------------------------- */
/* Common                                                                     */
/* -------------------------------------------------------------------------- */

/** Mirrors schemas/common.py Page[T]. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** Mirrors schemas/common.py Message. */
export interface Message {
  detail: string;
}

export interface Paginated {
  limit?: number;
  offset?: number;
}

/* -------------------------------------------------------------------------- */
/* Auth and user (schemas/auth.py, schemas/user.py)                            */
/* -------------------------------------------------------------------------- */

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface RegisterRequest {
  email: string;
  /** Backend enforces 10..72 characters. */
  password: string;
  full_name?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Profile {
  headline: string | null;
  location: string | null;
  phone: string | null;
  years_of_experience: number | null;
  summary: string | null;
  resume_text: string | null;
  resume_filename: string | null;
  skills: string[];
  preferred_languages: string[];
  answer_bank: Record<string, unknown>;
  updated_at: string | null;
}

export interface ProfileUpdate {
  headline?: string | null;
  location?: string | null;
  phone?: string | null;
  years_of_experience?: number | null;
  summary?: string | null;
  resume_text?: string | null;
  skills?: string[] | null;
  preferred_languages?: string[] | null;
  answer_bank?: Record<string, unknown> | null;
}

export interface UserSettings {
  daily_cap: number;
  min_score: number;
  action_delay_min: number;
  action_delay_max: number;
  apply_delay_min: number;
  apply_delay_max: number;
  working_hour_start: number;
  working_hour_end: number;
  require_manual_approval: boolean;
  dry_run: boolean;
  ai_model: string | null;
  cover_letter_tone: string;
  content_language: string;
  generate_cover_letter: boolean;
}

export type UserSettingsUpdate = Partial<UserSettings>;

/** Metadata only: cookies and credentials never cross the API. */
export interface LinkedInAccount {
  display_name: string | null;
  is_connected: boolean;
  last_verified_at: string | null;
}

export interface SessionStatus {
  browser_open: boolean;
  logged_in: boolean;
  blocked: boolean;
  blocked_reason: string | null;
  active_run_id: number | null;
  applications_today: number;
  daily_cap: number;
  dry_run: boolean;
  ai_configured: boolean;
}

/* -------------------------------------------------------------------------- */
/* Searches and jobs (schemas/job.py)                                         */
/* -------------------------------------------------------------------------- */

export interface SearchBase {
  name: string;
  keywords: string;
  location: string | null;
  remote_filter: string | null;
  experience_levels: string[];
  date_posted: string | null;
  easy_apply_only: boolean;
  max_results: number;
}

export interface Search extends SearchBase {
  id: number;
  is_active: boolean;
  last_run_at: string | null;
  created_at: string | null;
}

export interface SearchCreate {
  name: string;
  keywords: string;
  location?: string | null;
  remote_filter?: string | null;
  experience_levels?: string[];
  date_posted?: string | null;
  easy_apply_only?: boolean;
  max_results?: number;
}

export interface SearchUpdate {
  name?: string | null;
  keywords?: string | null;
  location?: string | null;
  remote_filter?: string | null;
  experience_levels?: string[] | null;
  date_posted?: string | null;
  easy_apply_only?: boolean | null;
  max_results?: number | null;
  is_active?: boolean | null;
}

export interface Job {
  id: number;
  external_id: string;
  title: string;
  company: string;
  location: string | null;
  url: string | null;
  workplace_type: string | null;
  easy_apply: boolean;
  status: JobStatus;
  score: number | null;
  score_reasons: string[];
  missing_requirements: string[];
  score_breakdown: ScoreDimension[];
  score_gates: ScoreGate[];
  skip_reason: string | null;
  detected_language: string | null;
  posted_at: string | null;
  created_at: string | null;
  search_id: number | null;
  application_id: number | null;
}

export interface JobDetail extends Job {
  description: string | null;
}

export interface JobListQuery extends Paginated {
  status?: JobStatus;
  min_score?: number;
  search_id?: number;
}

/* -------------------------------------------------------------------------- */
/* AI output (ai/schemas.py)                                                  */
/* -------------------------------------------------------------------------- */

export type ScoreDimensionName =
  | "skills"
  | "experience"
  | "seniority"
  | "education"
  | "location"
  | "language";

export interface ScoreDimension {
  dimension: ScoreDimensionName;
  score: number;
  weight: "hard" | "nice_to_have";
  evidence: string;
}

export type GateName = "eligibility" | "language";
export type GateStatus = "pass" | "fail" | "flag";

export interface ScoreGate {
  gate: GateName;
  status: GateStatus;
  evidence: string;
}

export interface StretchFlag {
  text: string;
  why_stretch: string;
}

export type ReviewCategory = "missed_keywords" | "company_angle" | "reframing" | "tone";
export type CoverageStatus = "covered" | "synonym_only" | "missing_have_it" | "missing_gap";

export interface SuggestedEdit {
  old_string: string;
  new_string: string;
  reason: string;
}

export interface ReviewNote {
  category: ReviewCategory;
  note: string;
}

export interface RequirementCoverage {
  requirement: string;
  status: CoverageStatus;
  note: string | null;
}

export interface DraftReview {
  edits: SuggestedEdit[];
  critique: ReviewNote[];
  coverage: RequirementCoverage[];
  summary: string | null;
}

export type AnswerSource = "answer_bank" | "ai" | "user";

export interface ScreeningAnswer {
  question: string;
  answer: string;
  question_type: QuestionType;
  confidence: AnswerConfidence;
  needs_review: boolean;
  reasoning: string | null;
  // Absent on answers stored before provenance existed.
  source?: AnswerSource;
  field_id: string | null;
}

export interface CoverLetterResponse {
  content: string;
  language: string;
}

export interface AIStatus {
  configured: boolean;
  model: string;
}

export interface CVChange {
  section: string;
  action: string;
  detail: string;
}

/** A resume adapted to one job — reorganized and re-emphasized, never invented. */
export interface TailoredResume {
  job_id: number;
  content: string;
  changes: CVChange[];
  /** Requirements the resume genuinely cannot back — surfaced, not invented. */
  unsupported_requirements: string[];
  /** Technologies in the tailored text but not the profile, for you to verify. */
  invention_flags: string[];
  /** Grounded but aggressive claims — keep, soften, or drop is your call. */
  stretch_flags: StretchFlag[];
  summary: string | null;
  model: string | null;
  was_edited: boolean;
  /** True when your profile changed after this draft was generated. */
  is_stale: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/* -------------------------------------------------------------------------- */
/* Applications (schemas/application.py)                                      */
/* -------------------------------------------------------------------------- */

export interface Application {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  cover_letter: string | null;
  /** Persisted as loose JSON; shaped like ScreeningAnswer. */
  screening_answers: ScreeningAnswer[];
  resume_filename: string | null;
  total_steps: number | null;
  current_step: number | null;
  needs_human_input: boolean;
  was_dry_run: boolean;
  approved_at: string | null;
  submitted_at: string | null;
  error_message: string | null;
  outcome: ApplicationOutcome | null;
  outcome_updated_at: string | null;
  outcome_note: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** A submitted application as it appears on the pipeline board. */
export interface ApplicationCard {
  id: number;
  job_id: number;
  title: string;
  company: string;
  location: string | null;
  score: number | null;
  outcome: ApplicationOutcome;
  submitted_at: string | null;
  outcome_updated_at: string | null;
}

export interface OutcomeUpdate {
  outcome: ApplicationOutcome;
  note?: string | null;
}

export interface OutcomeCount {
  outcome: ApplicationOutcome;
  count: number;
  avg_score: number | null;
}

export interface ScoreBandRate {
  /** e.g. "90-100" */
  label: string;
  total: number;
  interviews: number;
  rate: number | null;
}

export interface OutcomeStats {
  total_submitted: number;
  interviews: number;
  offers: number;
  rejected: number;
  ghosted: number;
  interview_rate: number | null;
  by_outcome: OutcomeCount[];
  interview_rate_by_band: ScoreBandRate[];
}

export interface ApplicationEvent {
  id: number;
  event_type: ApplicationEventType;
  message: string | null;
  payload: Record<string, unknown>;
  is_error: boolean;
  created_at: string;
}

export interface ApplicationDetail extends Application {
  job: Job | null;
  events: ApplicationEvent[];
}

/** User edits made during review, before approving the submission. */
export interface ApplicationUpdate {
  cover_letter?: string | null;
  screening_answers?: ScreeningAnswer[] | null;
}

export interface ApplicationListQuery extends Paginated {
  status?: ApplicationStatus;
}

/** Explicit consent for a single, already-reviewed application. */
export interface SubmitRequest {
  confirm: true;
}

/* -------------------------------------------------------------------------- */
/* Automation (schemas/automation.py)                                         */
/* -------------------------------------------------------------------------- */

export interface SearchRunRequest {
  search_id?: number | null;
  keywords?: string | null;
  location?: string | null;
  remote_filter?: string | null;
  date_posted?: string | null;
  experience_levels?: string[];
  max_results?: number;
  /** Search + AI analysis never submits anything; submitting is a separate step. */
  analyze?: boolean;
}

export interface PrepareRequest {
  job_ids: number[];
  /** Must be true once the user has reviewed the preview. */
  confirmed?: boolean;
}

export interface PreviewResponse {
  jobs_to_process: number;
  already_applied: number;
  below_threshold: number;
  remaining_today: number;
  daily_cap: number;
  dry_run: boolean;
  requires_confirmation: boolean;
  jobs: Job[];
  warnings: string[];
}

export interface AutomationRun {
  id: number;
  kind: AutomationRunKind;
  status: AutomationRunStatus;
  dry_run: boolean;
  search_id: number | null;
  jobs_found: number;
  jobs_analyzed: number;
  jobs_skipped: number;
  applications_prepared: number;
  applications_submitted: number;
  stop_requested: boolean;
  blocked_reason: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

/* -------------------------------------------------------------------------- */
/* Stats (schemas/stats.py)                                                   */
/* -------------------------------------------------------------------------- */

export interface ScoreBucket {
  /** e.g. "80-100" */
  label: string;
  count: number;
}

export interface DailyCount {
  /** ISO date, YYYY-MM-DD */
  date: string;
  count: number;
}

export interface DashboardStats {
  jobs_total: number;
  jobs_by_status: Partial<Record<JobStatus, number>> & Record<string, number>;
  applications_total: number;
  applications_today: number;
  awaiting_review: number;
  daily_cap: number;
  remaining_today: number;
  average_score: number | null;
  score_distribution: ScoreBucket[];
  applications_last_7_days: DailyCount[];
  ai_calls_total: number;
  ai_tokens_input: number;
  ai_tokens_output: number;
}

/* -------------------------------------------------------------------------- */
/* Misc                                                                      */
/* -------------------------------------------------------------------------- */

export interface HealthResponse {
  status: string;
  version: string;
}

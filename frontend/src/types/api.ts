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

/**
 * How an application reaches the employer.
 *
 * "easy_apply" is the LinkedIn form the automation fills and sends after you
 * approve it. "external" is a posting on the company's own site: the app
 * prepares the content, you submit it there, and then record that you did.
 */
export type ApplicationChannel = "easy_apply" | "external";

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
  | "resume_adapted"
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

/* -------------------------------------------------------------------------- */
/* What kind of vacancy this account is looking for                           */
/* -------------------------------------------------------------------------- */

/** The portal's own vocabulary, so a preference needs no translation table. */
export const SENIORITY_VALUES = [
  "internship",
  "entry",
  "associate",
  "mid-senior",
  "director",
  "executive",
] as const;
export type Seniority = (typeof SENIORITY_VALUES)[number];

export const WORK_MODELS = ["remote", "hybrid", "on-site"] as const;
export type WorkModel = (typeof WORK_MODELS)[number];

export interface JobPreferences {
  target_role: string | null;
  alternative_roles: string[];
  seniority: string[];
  work_models: string[];
  locations: string[];
  /** A floor, in whole currency units. */
  salary_min: number | null;
  salary_currency: string;
  priority_technologies: string[];
  /** Words that disqualify a posting outright, matched on title/location/workplace. */
  excluded_terms: string[];
  updated_at: string | null;
}

export type JobPreferencesUpdate = Partial<Omit<JobPreferences, "updated_at">>;

/**
 * Why one vacancy — as two lists, not as a number.
 *
 * `covered` carries the candidate's own spelling and `missing` the posting's,
 * because a technology they never wrote down has no spelling of theirs to use.
 * Every sentence about these is composed in the frontend.
 */
export interface Recommendation {
  verdict: string;
  score: number | null;
  covered: string[];
  missing: string[];
  /** The subset of `covered` the user asked to lead with. Never an addition. */
  prioritized: string[];
  covered_total: number;
  asked_total: number;
  coverage_pct: number;
  /** False when the posting named nothing comparable. */
  has_evidence: boolean;
}

/* -------------------------------------------------------------------------- */
/* Reading an uploaded resume                                                 */
/* -------------------------------------------------------------------------- */

/**
 * One position read out of an uploaded CV.
 *
 * `is_complete` is false when the layout hid the role or the employer, which is
 * the signal the confirm screen turns into "confira isto" instead of guessing.
 */
export interface ResumeIntakeExperience {
  role: string;
  company: string;
  employment_type: string | null;
  location: string | null;
  /** ISO date (YYYY-MM-DD). */
  started_on: string | null;
  ended_on: string | null;
  is_current: boolean;
  /** The period exactly as the document prints it. */
  period_text: string;
  summary: string;
  responsibilities: string[];
  technologies: string[];
  is_complete: boolean;
}

export interface ResumeIntakeEducation {
  institution: string;
  degree: string;
  period_text: string;
}

export interface ResumeIntakeProject {
  name: string;
  description: string;
  technologies: string[];
}

/** A proposal, never a saved profile: nothing here has been written. */
export interface ResumeIntake {
  full_name: string | null;
  headline: string | null;
  location: string | null;
  email: string | null;
  phone: string | null;
  summary: string | null;
  skills: string[];
  languages: string[];
  experiences: ResumeIntakeExperience[];
  education: ResumeIntakeEducation[];
  projects: ResumeIntakeProject[];
  certifications: string[];
  /** What could not be read. Shown as-is; the backend writes them in Portuguese. */
  warnings: string[];
  resume_text: string;
  resume_filename: string | null;
}

/** What the user confirmed. Fields left out are not touched. */
export interface IntakeApply {
  full_name?: string | null;
  headline?: string | null;
  location?: string | null;
  phone?: string | null;
  summary?: string | null;
  years_of_experience?: number | null;
  resume_text?: string | null;
  skills?: string[] | null;
  preferred_languages?: string[] | null;
  experiences?: ExperienceCreate[];
  /** Destructive: removes the positions this account already has. */
  replace_experiences?: boolean;
}

export interface IntakeApplied {
  profile: Profile;
  experiences_created: number;
  experiences_removed: number;
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
  /** Which portal the job came from ("linkedin", "gupy", ...). */
  source: string;
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
  /** Band the score falls in, derived on read: strong, good, moderate, weak, poor. */
  verdict: string | null;
  /** The score recomputed from the breakdown's own weights, or null when it cannot be. */
  weighted_score: number | null;
  /** Overall score minus the weighted one. Reported, never applied. */
  score_divergence: number | null;
  skip_reason: string | null;
  detected_language: string | null;
  posted_at: string | null;
  created_at: string | null;
  search_id: number | null;
  application_id: number | null;
  /**
   * Filled in only on the job list and one job's page — the two screens where
   * the reader is deciding whether to apply. Null elsewhere, and null for a
   * posting whose description has not been fetched yet.
   */
  recommendation?: Recommendation | null;
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
  /**
   * How much this dimension moved the overall score. Sums to 100 across a
   * breakdown scored after the field existed; 0 on every row stored before it.
   */
  weight_pct: number;
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

export type StageType =
  | "phone_screen"
  | "technical"
  | "case_study"
  | "final_round"
  | "offer_discussion";

export interface InterviewStage {
  id: number;
  application_id: number;
  stage_type: StageType | string;
  scheduled_at: string | null;
  completed_at: string | null;
  note: string | null;
  created_at: string | null;
}

export interface InterviewStageCreate {
  stage_type: StageType;
  scheduled_at?: string | null;
  note?: string | null;
}

export interface InterviewPrep {
  content: string;
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
/* Resumes: the master one, and one adapted copy per application              */
/* (schemas/resume.py)                                                        */
/* -------------------------------------------------------------------------- */

export interface ResumeProject {
  name: string;
  description: string;
  technologies: string[];
}

/** One position on the master resume — the only place a fact about you lives. */
export interface Experience {
  id: number;
  company: string;
  role: string;
  employment_type: string | null;
  location: string | null;
  /** ISO date (YYYY-MM-DD). */
  started_on: string | null;
  ended_on: string | null;
  is_current: boolean;
  summary: string | null;
  responsibilities: string[];
  technologies: string[];
  results: string[];
  projects: ResumeProject[];
  position: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExperienceCreate {
  company: string;
  role: string;
  employment_type?: string | null;
  location?: string | null;
  started_on?: string | null;
  ended_on?: string | null;
  is_current?: boolean;
  summary?: string | null;
  responsibilities?: string[];
  technologies?: string[];
  results?: string[];
  projects?: ResumeProject[];
  position?: number | null;
}

export type ExperienceUpdate = Partial<ExperienceCreate>;

export interface MasterResume {
  headline: string | null;
  location: string | null;
  summary: string | null;
  years_of_experience: number | null;
  skills: string[];
  resume_text: string | null;
  resume_filename: string | null;
  experiences: Experience[];
  /** Hash of everything above; an older snapshot compares itself against it. */
  fingerprint: string;
  updated_at: string | null;
}

/** A project one posting had a reason to see. */
export interface AdaptedProject extends ResumeProject {
  company: string;
  role: string;
  matched_terms: string[];
}

/**
 * One experience as a single application presents it.
 *
 * Same facts as the master position, reordered: `responsibilities` and `results`
 * lead with the sentences this posting asks about, and `technologies` leads with
 * the matched ones. `promoted` is how many of your own lines moved up.
 */
export interface AdaptedExperience {
  experience_id: number | null;
  company: string;
  role: string;
  location: string | null;
  employment_type: string | null;
  started_on: string | null;
  ended_on: string | null;
  is_current: boolean;
  summary: string;
  responsibilities: string[];
  technologies: string[];
  results: string[];
  projects: AdaptedProject[];
  relevance: number;
  matched_terms: string[];
  promoted: number;
}

/** Closed set; mirrors domain/resume.py CHANGE_KINDS. */
export type ResumeChangeKind =
  | "experience_prioritized"
  | "experience_refocused"
  | "skill_highlighted"
  | "technology_emphasized"
  | "project_selected";

export interface ResumeChange {
  kind: ResumeChangeKind | string;
  target: string;
  terms: string[];
  matched: number;
  total: number;
}

export type FitFactorName = "technologies" | "experience" | "skills" | "seniority";

export interface FitFactor {
  factor: FitFactorName | string;
  score: number;
  weight_pct: number;
  matched: number;
  total: number;
  terms: string[];
}

/** One position that changed place between the master and this copy. 1-based. */
export interface ExperienceMove {
  experience_id: number | null;
  company: string;
  role: string;
  from_position: number;
  to_position: number;
  promoted_bullets: number;
  matched_terms: string[];
}

/**
 * How far this copy is from the master — deliberately, how little.
 *
 * `invented` is measured by running the invention guard over the copy against
 * the master's own words, so an empty list is a result rather than a promise.
 * `is_comparable` is false when the master moved after this copy was frozen.
 */
export interface ResumeComparison {
  moves: ExperienceMove[];
  highlighted_technologies: string[];
  promoted_bullets: number;
  invented: string[];
  experiences_reordered: number;
  sections_adjusted: number;
  changes_total: number;
  is_clean: boolean;
  is_comparable: boolean;
}

export interface ApplicationResume {
  application_id: number;
  job_id: number;
  job_title: string | null;
  job_company: string | null;
  version: number;

  headline: string | null;
  summary: string | null;
  skills: string[];
  highlighted_skills: string[];
  emphasized_technologies: string[];
  experiences: AdaptedExperience[];
  projects: AdaptedProject[];
  changes: ResumeChange[];

  /** Empty `fit_factors` means the posting named nothing recognisable — hide the figure. */
  fit_score: number;
  fit_factors: FitFactor[];
  uncovered_requirements: string[];

  /** Only on the single-application read; the version list is metadata. */
  comparison?: ResumeComparison | null;

  model: string | null;
  was_edited: boolean;
  /** True when the master resume changed after this copy was derived. */
  is_stale: boolean;
  adapted_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** The parts of one adapted experience the reviewer may rewrite. */
export interface AdaptedExperienceEdit {
  summary: string;
  responsibilities: string[];
  technologies: string[];
  results: string[];
}

export interface ApplicationResumeUpdate {
  headline?: string | null;
  summary?: string | null;
  skills?: string[] | null;
  /** Positional: must be the same length as the stored list, or the server refuses. */
  experiences?: AdaptedExperienceEdit[] | null;
}

export interface ResumeVersionSummary {
  application_id: number;
  job_id: number;
  job_title: string;
  job_company: string;
  application_status: ApplicationStatus;
  version: number;
  fit_score: number;
  has_fit: boolean;
  highlighted_count: number;
  was_edited: boolean;
  is_stale: boolean;
  updated_at: string | null;
}

/* -------------------------------------------------------------------------- */
/* Applications (schemas/application.py)                                      */
/* -------------------------------------------------------------------------- */

export interface Application {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  /** Which completion path this application may take. */
  channel: ApplicationChannel;
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

export interface PortalSearchResult {
  portal: string;
  jobs_found: number;
  jobs_new: number;
}

export interface SegmentRate {
  label: string;
  total: number;
  interviews: number;
  rate: number | null;
}

export interface SegmentStats {
  by_company: SegmentRate[];
  by_location: SegmentRate[];
  by_workplace: SegmentRate[];
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

/**
 * The record that you applied on the company's own site.
 *
 * `confirm` mirrors SubmitRequest so this cannot fire by accident — but it
 * consents to writing something down, not to sending anything.
 */
export interface MarkAppliedRequest {
  confirm: true;
  note?: string | null;
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
  /** An interrupted run whose inputs survived — it can pick up where it stopped. */
  resumable: boolean;
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

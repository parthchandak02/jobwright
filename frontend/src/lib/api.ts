export const API_BASE = '/api'

/** Error from the API with HTTP status and optional machine code (e.g. no_profile). */
export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = res.statusText
  let code: string | undefined
  try {
    const body = await res.json()
    const d = body.detail
    if (d && typeof d === 'object') {
      code = d.code
      detail = d.detail || JSON.stringify(d)
    } else {
      detail = d || JSON.stringify(body)
    }
    code = code || body.code
  } catch {
    /* ignore */
  }
  return new ApiError(detail, res.status, code)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) throw await toApiError(res)
  return res.json() as Promise<T>
}

async function sendForm<T>(path: string, body: FormData, method: 'PUT' | 'POST'): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method, credentials: 'include', body })
  if (!res.ok) throw await toApiError(res)
  return res.json() as Promise<T>
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  return sendForm<T>(path, body, 'PUT')
}

/** Path segment for a job: the 12-char job_id (URL-safe), falling back to the encoded url. */
export function jobPath(job: { job_id?: string | null; url: string } | string): string {
  if (typeof job === 'string') return `/jobs/${encodeURIComponent(job)}`
  return `/jobs/${job.job_id || encodeURIComponent(job.url)}`
}

export type JobCard = {
  job_id: string
  whatsapp_notified_at: string | null
  url: string
  title: string | null
  company: string | null
  site: string | null
  location: string | null
  salary: string | null
  work_model: string | null
  sponsorship_status: 'required' | 'not_required' | 'not_found'
  fit_score: number | null
  ai_fit_score?: number | null
  user_fit_score?: number | null
  user_score_rationale?: string | null
  user_score_at?: string | null
  score_user_modified?: boolean
  keywords: string
  reasoning: string
  funnel_stage: string
  outcome: string | null
  is_dead?: boolean
  source: string
  applied_manually: boolean
  applied_at: string | null
  first_response_at: string | null
  follow_up_at: string | null
  followed_up_at?: string | null
  followup_due?: boolean
  applied_days_ago?: number | null
  followup_due_at?: string | null
  notes: string | null
  board_updated_by: string | null
  board_updated_at: string | null
  has_resume: boolean
  has_cover: boolean
  application_url: string | null
  discovered_at: string | null
  apply_status: string | null
  full_description?: string
  score_confidence?: number | null
  score_tier?: string | null
  score_model?: string | null
  dealbreakers?: string[]
  concerns?: string[]
  score_caps?: string[]
  location_ok?: boolean | null
  seniority?: string | null
  close_reason?: string | null
  duplicate_of?: { job_id: string; title: string | null; company: string | null } | null
  tailored_resume_path?: string | null
  tailored_resume_docx_path?: string | null
  cover_letter_path?: string | null
  cover_letter_docx_path?: string | null
}

export type BoardResponse = {
  stages: string[]
  columns: Record<string, JobCard[]>
  total: number
  closed_total?: number
}

export type Profile = {
  user_id: string
  name: string
  apply_enabled: boolean
  schedule?: string
  schedule_label?: string
  timezone?: string
  whatsapp_target?: string
  whatsapp_chat_name?: string
  weekly_summary?: boolean
  followup_days?: number
  brief_cron_name?: string
  cron_synced?: boolean
  cron_id?: string | null
  cron_error?: string | null
  stats: Record<string, number>
  stage_counts: Record<string, number>
  source: string
}

export type QueryEntry = { query: string; tier: number }
export type LocationEntry = { location: string; remote: boolean }

export type SettingsProfile = {
  personal: Record<string, string>
  compensation: Record<string, string>
  experience: Record<string, string>
  job_preferences: {
    ideal_roles?: string[]
    seek?: string
    avoid_roles?: string[]
    company_types?: string
  }
}

export type SettingsSearches = {
  queries: QueryEntry[]
  locations: LocationEntry[]
  boards: string[]
  exclude_titles: string[]
  min_salary: number | null
  hours_old: number | null
  results_per_site: number | null
}

export type CoverLetterExample = {
  id: string
  filename: string
  kind: 'pdf' | 'txt'
  mtime: number
  markdown: string
}

export type SettingsData = {
  user_id: string
  name: string
  profile: SettingsProfile
  searches: SettingsSearches
  resume_markdown: string
  has_resume_pdf: boolean
  resume_pdf_mtime: number | null
  cover_letter_examples: CoverLetterExample[]
}

export const STAGE_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  prepare: 'Prepare',
  applied: 'Applied',
  in_progress: 'In Progress',
  offer: 'Offer',
  closed: 'Closed',
}

/** Kanban lane order (matches backend FUNNEL_STAGES). */
export const FUNNEL_STAGES = [
  'backlog',
  'prepare',
  'applied',
  'in_progress',
  'offer',
  'closed',
] as const

export type FunnelStage = (typeof FUNNEL_STAGES)[number]

/** CSS custom-property names for per-lane accents (defined in index.css). */
export const STAGE_TONE: Record<string, string> = {
  backlog: '--stage-backlog',
  prepare: '--stage-prepare',
  applied: '--stage-applied',
  in_progress: '--stage-in-progress',
  offer: '--stage-offer',
  closed: '--stage-closed',
}

/** Resolved lane color for headers, card tints, etc. */
export function laneTone(stage: string): string {
  const token = STAGE_TONE[stage] || STAGE_TONE.backlog
  return `var(${token})`
}

export const OUTCOMES = ['not_interested', 'rejected', 'withdrawn', 'ghosted', 'accepted', 'cancelled'] as const

export const OUTCOME_LABELS: Record<string, string> = {
  not_interested: 'Not for me',
  rejected: 'They said no',
  withdrawn: 'I withdrew',
  ghosted: 'No response',
  accepted: 'Accepted an offer',
  cancelled: 'Posting closed',
  duplicate: 'Duplicate posting',
}

/** Handle returned when a pipeline run is started. */
export type RunHandle = {
  run_id: string
  pid: number
  log_path: string
  user: string
  stages: string[]
  kind?: string
  job_id?: string | null
}

/** Full run record from GET /api/runs. */
export type RunRecord = RunHandle & {
  started_at: string
  running: boolean
  returncode: number | null
}

export type StopRunResponse = {
  run_id: string
  stopped: boolean
  returncode: number | null
}

export type StartRunOptions = { min_score?: number; workers?: number }

/** Start a pipeline run; returns the process handle (run id, pid, log path). */
export function startRun(stages: string[], opts?: StartRunOptions): Promise<RunHandle> {
  return apiFetch<RunHandle>('/run', {
    method: 'POST',
    body: JSON.stringify({
      stages,
      min_score: opts?.min_score ?? 7,
      workers: opts?.workers ?? 4,
    }),
  })
}

export type TailorInstructions = {
  resume_instructions: string
  cover_instructions: string
}

export function tailorDefaults(): Promise<TailorInstructions> {
  return apiFetch<TailorInstructions>('/tailor/defaults')
}

/** Start a verbose per-job tailor + cover + docx run (``key`` = job_id or url). */
export function startJobTailor(key: string, instructions?: Partial<TailorInstructions>): Promise<RunHandle> {
  return apiFetch<RunHandle>(`${jobPath(key)}/tailor`, {
    method: 'POST',
    body: JSON.stringify({
      resume_instructions: instructions?.resume_instructions,
      cover_instructions: instructions?.cover_instructions,
    }),
  })
}

/** Resume-only tailor (tailor + docx). */
export function startJobTailorResume(key: string, resumeInstructions?: string): Promise<RunHandle> {
  return apiFetch<RunHandle>(`${jobPath(key)}/tailor/resume`, {
    method: 'POST',
    body: JSON.stringify({ resume_instructions: resumeInstructions }),
  })
}

/** Cover-only tailor (cover + docx). */
export function startJobTailorCover(key: string, coverInstructions?: string): Promise<RunHandle> {
  return apiFetch<RunHandle>(`${jobPath(key)}/tailor/cover`, {
    method: 'POST',
    body: JSON.stringify({ cover_instructions: coverInstructions }),
  })
}

/** Stop a running pipeline process. */
export function stopRun(runId: string): Promise<StopRunResponse> {
  return apiFetch<StopRunResponse>(`/runs/${runId}/stop`, { method: 'POST' })
}

/** List known runs (newest first). */
export function listRuns(): Promise<RunRecord[]> {
  return apiFetch<{ runs: RunRecord[] }>('/runs').then((r) => r.runs)
}

export type NotifyResponse = {
  sent: number
  skipped: boolean
  reason?: string
  message?: string
  jobs: { job_id: string; title: string | null; company: string | null }[]
}

/** Trigger the WhatsApp notify digest for newly surfaced jobs. */
export function notifyWhatsApp(): Promise<NotifyResponse> {
  return apiFetch<NotifyResponse>('/notify', { method: 'POST' })
}

export function updateProfile(body: {
  schedule?: string
  whatsapp_target?: string
  weekly_summary?: boolean
  followup_days?: number
}): Promise<Profile> {
  return apiFetch<Profile>('/profile', { method: 'PUT', body: JSON.stringify(body) })
}


// ---------------------------------------------------------------------------
// Identity, onboarding, quality, WhatsApp, admin
// ---------------------------------------------------------------------------

export type Me = {
  email: string
  is_admin: boolean
  auth_mode: 'cloudflare' | 'dev'
  active_user: string | null
  profiles: { user_id: string; name: string }[]
  can_create_profile: boolean
}

export const getMe = () => apiFetch<Me>('/me')

export function switchProfile(userId: string): Promise<Profile> {
  return apiFetch<Profile>('/session', { method: 'POST', body: JSON.stringify({ user_id: userId }) })
}

export type OnboardingSteps = {
  resume: boolean
  profile: boolean
  criteria: boolean
  searches: boolean
  cover_letters: boolean
  whatsapp: boolean
  schedule: boolean
  first_run: boolean
}

export type OnboardingStatus = {
  email: string
  has_profile: boolean
  user_id?: string
  steps: Partial<OnboardingSteps>
  complete: boolean
}

export const getOnboardingStatus = () => apiFetch<OnboardingStatus>('/onboarding/status')

export function createProfile(name: string, emails?: string[]): Promise<{ user_id: string; name: string; access_sync?: AccessSyncResult }> {
  return apiFetch('/onboarding/profile', { method: 'POST', body: JSON.stringify({ name, emails }) })
}

export type Dealbreaker = { id: string; label: string; description: string }

export type MatchCriteria = {
  summary: string
  dealbreakers: Dealbreaker[]
  must_haves: string[]
  nice_to_haves: string[]
  locations_ok: string[]
  locations_not_ok: string[]
  seniority: string
  min_salary: number | null
  notify_threshold: number
}

export type OnboardingDraft = {
  profile: {
    personal: Record<string, string>
    experience: Record<string, string>
    job_preferences: { ideal_roles: string[]; avoid_roles: string[]; seek?: string; company_types?: string }
    compensation?: Record<string, string>
  }
  criteria: MatchCriteria
  searches: {
    queries: QueryEntry[]
    locations: LocationEntry[]
    boards: string[]
    min_salary: number | null
  }
}

export type DraftHints = { target_roles?: string; locations?: string; min_salary?: string; avoid?: string }

export function draftSetup(file: File | null, hints: DraftHints): Promise<OnboardingDraft> {
  const body = new FormData()
  if (file) body.append('file', file)
  for (const [k, v] of Object.entries(hints)) body.append(k, v ?? '')
  return sendForm<OnboardingDraft>('/onboarding/draft', body, 'POST')
}

export function confirmSetup(draft: OnboardingDraft): Promise<OnboardingStatus> {
  return apiFetch('/onboarding/confirm', { method: 'POST', body: JSON.stringify(draft) })
}

export const getCriteria = () => apiFetch<{ criteria: MatchCriteria; derived: boolean }>('/criteria')

export function saveCriteria(criteria: MatchCriteria) {
  return apiFetch<{ criteria: MatchCriteria; derived: boolean }>('/criteria', {
    method: 'PUT',
    body: JSON.stringify({ criteria }),
  })
}

export const suggestCriteria = () =>
  apiFetch<{ criteria: MatchCriteria; based_on_ratings: number }>('/criteria/suggest', { method: 'POST' })

export type WhatsAppChat = {
  target: string
  id: string
  name: string
  type: 'group' | 'dm'
  participants: number | null
  includes_you: boolean
}

export type WhatsAppChats = {
  bridge: string
  chats: WhatsAppChat[]
  direct_target: string | null
  filtered: boolean
}

export function listWhatsAppChats(phone?: string): Promise<WhatsAppChats> {
  const q = phone ? `?phone=${encodeURIComponent(phone)}` : ''
  return apiFetch<WhatsAppChats>(`/whatsapp/chats${q}`)
}

export function sendWhatsAppTest(target = '') {
  return apiFetch<{ ok: boolean; target: string }>('/whatsapp/test', {
    method: 'POST',
    body: JSON.stringify(target ? { target } : {}),
  })
}

export type LabelEntry = {
  id: number
  label_score: number
  verdict: string
  reasons: string[]
  rationale: string | null
  source: string
  actor: string | null
  model_score: number | null
  created_at: string
}

export type JobLabels = {
  labels: LabelEntry[]
  machine_scores: {
    score: number
    confidence: number | null
    tier: string | null
    model: string | null
    prompt_version: string | null
    run_kind: string | null
    created_at: string
  }[]
}

export const getJobLabels = (job: JobCard) => apiFetch<JobLabels>(`${jobPath(job)}/labels`)

export type StageHistoryEntry = { from_stage: string | null; to_stage: string; actor: string; at: string; note: string | null }

export const getJobHistory = (job: JobCard) =>
  apiFetch<{ history: StageHistoryEntry[] }>(`${jobPath(job)}/history`)

export function rateJob(job: JobCard, score: number, reasons: string[], note?: string) {
  return apiFetch<JobCard>(jobPath(job), {
    method: 'PATCH',
    body: JSON.stringify({ user_fit_score: score, user_score_reasons: reasons, user_score_rationale: note || '' }),
  })
}

export function clearRating(job: JobCard) {
  return apiFetch<JobCard>(jobPath(job), { method: 'PATCH', body: JSON.stringify({ clear_user_score: true }) })
}

export function moveJob(
  job: JobCard,
  toStage: string,
  opts?: { outcome?: string; reasons?: string[]; close_reason?: string },
) {
  return apiFetch<{ from_stage: string; job: JobCard }>(`${jobPath(job)}/move`, {
    method: 'POST',
    body: JSON.stringify({ to_stage: toStage, ...(opts || {}) }),
  })
}

export function followUpJob(job: JobCard, action: 'followed_up' | 'no_response') {
  return apiFetch<JobCard>(`${jobPath(job)}/followup`, { method: 'POST', body: JSON.stringify({ action }) })
}

export type EvalMetrics = {
  threshold: number
  predicted_pos: number
  tp: number
  fp: number
  fn: number
  precision: number
  recall: number
  f05: number
}

export type QualitySummary = {
  labels_total: number
  labels_30d: number
  eval_set: { size: number; relevant: number }
  notified_30d: number
  notified_advanced_30d: number
  latest_eval: null | {
    run_id: string
    at: string
    prompt_version: string
    config: Record<string, unknown>
    metrics: Record<string, EvalMetrics>
    metrics_explicit: Record<string, EvalMetrics>
    baseline: Record<string, EvalMetrics>
    baseline_explicit: Record<string, EvalMetrics>
    errors: number
  }
  recommended_threshold: null | {
    threshold: number
    meets_bar: boolean
    min_precision: number
    precision: number
    recall: number
    current: number
  }
  usage_30d: { purpose: string; prompt_tokens: number; completion_tokens: number; cost_usd: number | null }[]
}

export const getQuality = () => apiFetch<QualitySummary>('/quality')
export const startEval = () => apiFetch<RunHandle>('/quality/eval', { method: 'POST' })
export const startRescore = () => apiFetch<RunHandle>('/quality/rescore', { method: 'POST' })

export type AppStatus = {
  last_run: null | {
    started_at: string
    finished_at: string
    ok: boolean
    errors: Record<string, string>
    stages_requested: string[]
  }
  health: null | { at: string; level: 'ok' | 'warn' | 'fail'; lines: string[] }
  whatsapp_bridge: string
}

export const getStatus = () => apiFetch<AppStatus>('/status')

export type HealthLevel = 'ok' | 'warn' | 'fail' | null

export type AdminOverviewUser = {
  user_id: string
  name: string
  emails: string[]
  setup_complete: boolean
  health: { level: HealthLevel; lines: string[] } | null
  last_brief: { at: string | null; notified: number | null; status: 'ok' | 'failed' | 'skipped' | null } | null
  whatsapp: { target: string | null; name: string | null; type: 'group' | 'dm' | null }
  schedule: string
  schedule_label: string
  hour: number | null
  minute: number | null
  notify_threshold: number | null
  recommended_threshold: number | null
  brief_top_n: number
  human_gate: boolean
  weekly_summary: boolean
  followup_days: number
  counts: { new_7d: number; sent_7d: number; applied_total: number; open: number; followups_due: number }
  cost_30d: { tokens: number; cost_usd: number | null }
  hermes_status: 'unchanged' | 'add' | 'update' | 'skipped' | null
  brief_cron: boolean | null
  error: string | null
}

export type AdminOverview = {
  bridge: string
  access: { configured: boolean; in_sync: boolean; add: string[]; remove: string[]; error: string | null }
  hermes: { changed: boolean; pending: number; error: string | null }
  settings: { admins: string[]; ops_target: string; ops_target_name: string | null }
  users: AdminOverviewUser[]
}

export const getAdminOverview = () => apiFetch<AdminOverview>('/admin/overview')

export type AdminUserPatch = Partial<{
  name: string
  emails: string[]
  whatsapp_target: string
  hour: number
  minute: number
  schedule: string
  notify_threshold: number
  brief_top_n: number
  human_gate: boolean
  weekly_summary: boolean
  followup_days: number
}>

export type AdminCronResult = null | { ok?: boolean; error?: string | null; [k: string]: unknown }

export function patchAdminUser(userId: string, body: AdminUserPatch) {
  return apiFetch<{ user?: AdminOverviewUser; access_sync?: AccessSyncResult; cron?: AdminCronResult }>(
    `/admin/users/${encodeURIComponent(userId)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function sendAdminTestMessage(userId: string) {
  return apiFetch<{ sent: boolean; target: string }>(`/admin/users/${encodeURIComponent(userId)}/test-message`, {
    method: 'POST',
    body: '{}',
  })
}

export function startAdminRun(userId: string) {
  return apiFetch<RunHandle>(`/admin/users/${encodeURIComponent(userId)}/run`, { method: 'POST', body: '{}' })
}

export function deleteAdminUser(userId: string, deleteData = false) {
  return apiFetch(`/admin/users/${encodeURIComponent(userId)}?delete_data=${deleteData}`, { method: 'DELETE' })
}

export type UsageTotals = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  calls: number
  cost_usd: number | null
}
export type AdminCosts = {
  days: number
  users: (UsageTotals & { user_id: string; name: string; error: string | null })[]
  total: UsageTotals
}
export const getAdminCosts = (days = 30) => apiFetch<AdminCosts>(`/admin/costs?days=${days}`)

export type AdminSettings = { admins: string[]; ops_target: string; access_sync?: AccessSyncResult }
export const getAdminSettings = () => apiFetch<AdminSettings>('/admin/settings')
export function putAdminSettings(body: Partial<AdminSettings>) {
  return apiFetch<AdminSettings>('/admin/settings', { method: 'PUT', body: JSON.stringify(body) })
}
export const ensureWatchdog = () => apiFetch<{ ok: boolean; error?: string }>('/admin/watchdog', { method: 'POST' })
export const sendOpsTest = () => apiFetch<{ result: string }>('/admin/ops-test', { method: 'POST' })

export type AccessSyncResult = null | { ok: boolean; applied?: boolean; add?: string[]; remove?: string[]; error?: string }
export type AccessPlan = {
  configured: boolean
  error?: string
  app?: { id: string; name: string; domain: string }
  managed_policy?: { id: string | null; name: string; exists: boolean }
  current?: string[]
  desired?: string[]
  add?: string[]
  remove?: string[]
  other_policies_emails?: string[]
  in_sync?: boolean
  applied?: boolean
  created?: boolean
}
export const syncAccess = () => apiFetch<AccessPlan>('/admin/access/sync', { method: 'POST' })
export type HermesChannelEntry = {
  user_id: string
  name: string
  jid: string
  status: 'add' | 'update' | 'unchanged'
  changes: string[]
}
export type HermesChannelsPlan = {
  config_path: string
  entries: HermesChannelEntry[]
  skipped: { user_id: string; name: string; reason: string }[]
  orphans: string[]
  changed: boolean
  diff: string
  backup?: string | null
  written?: boolean
  dry_run?: boolean
}
export const applyHermesChannels = () =>
  apiFetch<HermesChannelsPlan>('/admin/hermes-channels/apply', { method: 'POST', body: '{}' })

export const previewNotify = () => apiFetch<NotifyResponse & { dry_run?: boolean }>('/notify/preview')

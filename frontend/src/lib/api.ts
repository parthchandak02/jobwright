export const API_BASE = '/api'

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    credentials: 'include',
    body,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const parsed = await res.json()
      detail = parsed.detail || JSON.stringify(parsed)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
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
  source: string
  applied_manually: boolean
  applied_at: string | null
  first_response_at: string | null
  follow_up_at: string | null
  notes: string | null
  board_updated_by: string | null
  board_updated_at: string | null
  has_resume: boolean
  has_cover: boolean
  application_url: string | null
  discovered_at: string | null
  apply_status: string | null
  full_description?: string
  tailored_resume_path?: string | null
  tailored_resume_docx_path?: string | null
  cover_letter_path?: string | null
  cover_letter_docx_path?: string | null
}

export type BoardResponse = {
  stages: string[]
  columns: Record<string, JobCard[]>
  total: number
}

export type Profile = {
  user_id: string
  name: string
  apply_enabled: boolean
  schedule?: string
  schedule_label?: string
  timezone?: string
  whatsapp_target?: string
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

export const OUTCOMES = ['accepted', 'rejected', 'withdrawn', 'ghosted', 'cancelled'] as const

/** Handle returned when a pipeline run is started. */
export type RunHandle = {
  run_id: string
  pid: number
  log_path: string
  user: string
  stages: string[]
  kind?: string
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

/** Start a verbose per-job tailor + cover + docx run. */
export function startJobTailor(url: string, instructions?: Partial<TailorInstructions>): Promise<RunHandle> {
  return apiFetch<RunHandle>(`/jobs/${encodeURIComponent(url)}/tailor`, {
    method: 'POST',
    body: JSON.stringify({
      resume_instructions: instructions?.resume_instructions,
      cover_instructions: instructions?.cover_instructions,
    }),
  })
}

/** Resume-only tailor (tailor + docx). */
export function startJobTailorResume(url: string, resumeInstructions?: string): Promise<RunHandle> {
  return apiFetch<RunHandle>(`/jobs/${encodeURIComponent(url)}/tailor/resume`, {
    method: 'POST',
    body: JSON.stringify({ resume_instructions: resumeInstructions }),
  })
}

/** Cover-only tailor (cover + docx). */
export function startJobTailorCover(url: string, coverInstructions?: string): Promise<RunHandle> {
  return apiFetch<RunHandle>(`/jobs/${encodeURIComponent(url)}/tailor/cover`, {
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
}): Promise<Profile> {
  return apiFetch<Profile>('/profile', { method: 'PUT', body: JSON.stringify(body) })
}

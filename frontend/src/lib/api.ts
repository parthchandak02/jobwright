export const API_BASE = '/api'

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
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

export type JobCard = {
  url: string
  title: string | null
  company: string | null
  site: string | null
  location: string | null
  salary: string | null
  work_model: string | null
  fit_score: number | null
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
  stats: Record<string, number>
  stage_counts: Record<string, number>
  source: string
}

export const STAGE_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  prepare: 'Prepare',
  applied: 'Applied',
  in_progress: 'In Progress',
  offer: 'Offer',
  closed: 'Closed',
}

/** CSS custom-property names for per-lane accents (defined in index.css). */
export const STAGE_TONE: Record<string, string> = {
  backlog: '--stage-backlog',
  prepare: '--stage-prepare',
  applied: '--stage-applied',
  in_progress: '--stage-in-progress',
  offer: '--stage-offer',
  closed: '--stage-closed',
}

export const OUTCOMES = ['accepted', 'rejected', 'withdrawn', 'ghosted', 'cancelled'] as const

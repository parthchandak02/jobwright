/** Global search (⌘F / Ctrl+F): the shortcut, the page list and the job search call. */
import { apiFetch, STAGE_LABELS } from '@/lib/api'

export type JobHit = {
  job_id: string
  url: string
  title: string | null
  company: string | null
  location: string | null
  funnel_stage: string
  outcome: string | null
  fit_score: number | null
  /** Words around the match when it was only in the description or notes. */
  snippet: string | null
}

export type SearchResponse = { query: string; results: JobHit[]; total: number }

export function searchJobs(q: string, signal?: AbortSignal): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(`/search?q=${encodeURIComponent(q)}`, { signal })
}

type KeyLike = Pick<KeyboardEvent, 'key' | 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey'>

/** ⌘F on a Mac, Ctrl+F elsewhere (either works anywhere; nobody uses the other one for something else). */
export function isFindShortcut(e: KeyLike): boolean {
  return (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'f'
}

export type PageHit = {
  /** Where it goes: path plus query string. */
  to: string
  label: string
  /** Where it lives, e.g. "Settings" for a settings tab. */
  group?: string
  /** Other words people search for. */
  keywords?: string
  adminOnly?: boolean
}

const STAGE_PAGES: PageHit[] = Object.entries(STAGE_LABELS).map(([stage, label]) => ({
  to: `/?stage=${stage}`,
  label,
  group: 'Jobs',
  keywords: 'stage lane column',
}))

export const PAGES: PageHit[] = [
  { to: '/', label: 'All jobs', keywords: 'board home table list' },
  ...STAGE_PAGES,
  { to: '/review', label: 'Quick review', keywords: 'swipe new triage' },
  { to: '/quality', label: 'Match quality', keywords: 'scores accuracy calibration' },
  { to: '/admin', label: 'Admin', keywords: 'profiles people users', adminOnly: true },
  { to: '/profile?tab=search', label: 'Search', group: 'Settings', keywords: 'queries titles locations sites' },
  { to: '/profile?tab=rules', label: 'Match rules', group: 'Settings', keywords: 'dealbreakers criteria fit' },
  { to: '/profile?tab=documents', label: 'Documents', group: 'Settings', keywords: 'resume cv cover letter pdf' },
  { to: '/profile?tab=whatsapp', label: 'Daily list', group: 'Settings', keywords: 'whatsapp schedule brief' },
  { to: '/profile?tab=about', label: 'About you', group: 'Settings', keywords: 'profile visa sponsorship salary' },
  { to: '/profile?tab=applying', label: 'Applications', group: 'Settings', keywords: 'answers auto apply' },
  { to: '/profile?tab=claude', label: 'Claude', group: 'Settings', keywords: 'connector mcp ai' },
]

export function terms(q: string): string[] {
  return q.toLowerCase().split(/\s+/).filter(Boolean)
}

/** Pages whose name (or keywords) contain every word; name matches first. At most `max`. */
export function matchPages(q: string, isAdmin: boolean, max = 4): PageHit[] {
  const words = terms(q)
  if (!words.length) return []
  const scored: { page: PageHit; score: number }[] = []
  for (const page of PAGES) {
    if (page.adminOnly && !isAdmin) continue
    const name = `${page.label} ${page.group ?? ''}`.toLowerCase()
    const all = `${name} ${page.keywords ?? ''}`
    if (!words.every((w) => all.includes(w))) continue
    const inName = words.filter((w) => name.includes(w)).length
    const starts = page.label.toLowerCase().startsWith(words[0]) ? 1 : 0
    scored.push({ page, score: inName * 2 + starts })
  }
  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, max)
    .map((s) => s.page)
}

/** Split `text` into plain and matching pieces so the matching words can be marked. */
export function highlight(text: string, q: string): { text: string; match: boolean }[] {
  // Single letters would mark half the text: only words of 2+ letters are marked.
  const words = terms(q).filter((w) => w.length > 1)
  if (!text || !words.length) return [{ text, match: false }]
  const lower = text.toLowerCase()
  const marks = new Array<boolean>(text.length).fill(false)
  for (const w of words) {
    let i = lower.indexOf(w)
    while (i >= 0) {
      for (let k = i; k < i + w.length; k++) marks[k] = true
      i = lower.indexOf(w, i + w.length)
    }
  }
  const out: { text: string; match: boolean }[] = []
  for (let i = 0; i < text.length; i++) {
    const last = out[out.length - 1]
    if (last && last.match === marks[i]) last.text += text[i]
    else out.push({ text: text[i], match: marks[i] })
  }
  return out
}

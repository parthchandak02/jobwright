import type { PendingInput } from '@/lib/api'

/** Open questions grouped by the job they came from, newest job first (Settings → About you). */
export type QuestionGroup = {
  key: string
  company: string
  jobId: string | null
  questions: PendingInput[]
}

export function questionGroups(pending: PendingInput[]): QuestionGroup[] {
  const groups = new Map<string, QuestionGroup>()
  for (const p of pending) {
    if (p.kind !== 'answer' || p.status !== 'open') continue
    const key = p.job_id || p.company || 'other'
    let group = groups.get(key)
    if (!group) {
      group = { key, company: p.company || 'An application', jobId: p.job_id, questions: [] }
      groups.set(key, group)
    }
    group.questions.push(p)
  }
  return [...groups.values()]
}

/** How to ask: a few choices as buttons, many as a list, none as a text box. */
export function answerControl(choices: string[] | undefined): 'buttons' | 'select' | 'text' {
  const n = (choices ?? []).filter((c) => c.trim()).length
  if (!n) return 'text'
  return n <= 3 ? 'buttons' : 'select'
}

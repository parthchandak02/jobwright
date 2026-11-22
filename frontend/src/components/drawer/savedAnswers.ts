import type { AnswerSectionId, ApplicationAnswers } from '@/lib/api'
import { SECTION_ORDER, shortLabel } from '@/lib/applicationDetails'

/** Only these four answer sections belong in the job drawer (never contact, diversity, or other). */
export const SAVED_ANSWER_SECTIONS = ['education', 'eligibility', 'experience', 'pay_start'] as const satisfies readonly AnswerSectionId[]
const ALLOWED_SECTIONS = new Set<string>(SAVED_ANSWER_SECTIONS)

export type SavedAnswerItem = { key: string; label: string; value: string; hintLabel?: string }
export type SavedAnswerSection = { id: (typeof SAVED_ANSWER_SECTIONS)[number]; title: string; items: SavedAnswerItem[] }

/** Group non-empty saved answers under API section titles; contact, diversity, other and custom are excluded. */
export function pickSavedAnswers(
  data: Pick<ApplicationAnswers, 'answers' | 'fields' | 'sections'> | null | undefined,
): SavedAnswerSection[] {
  if (!data || typeof data !== 'object' || !data.answers || typeof data.answers !== 'object') return []
  const fields = Array.isArray(data.fields) ? data.fields : []
  const order = data.sections?.length ? data.sections : SECTION_ORDER

  const result: SavedAnswerSection[] = []
  for (const section of order) {
    if (!ALLOWED_SECTIONS.has(section.id)) continue
    const items: SavedAnswerItem[] = []
    for (const field of fields) {
      if ((field.section ?? 'other') !== section.id) continue
      if (!Object.prototype.hasOwnProperty.call(data.answers, field.key)) continue
      const raw = data.answers[field.key]?.value
      const value = typeof raw === 'string' ? raw.trim() : ''
      if (!value) continue
      const label = shortLabel(field)
      items.push({ key: field.key, label, value, hintLabel: label !== field.label ? field.label : undefined })
    }
    if (items.length) result.push({ id: section.id as SavedAnswerSection['id'], title: section.title, items })
  }
  return result
}

/** Short labels of missing required answers in the drawer's four sections, in field order. */
export function pickMissingAnswers(
  data: Pick<ApplicationAnswers, 'missing' | 'fields'> | null | undefined,
): string[] {
  if (!data || typeof data !== 'object' || !Array.isArray(data.missing) || !data.missing.length) return []
  const missing = new Set(data.missing)
  const fields = Array.isArray(data.fields) ? data.fields : []
  const labels: string[] = []
  for (const field of fields) {
    if (!ALLOWED_SECTIONS.has(field.section ?? 'other')) continue
    if (!missing.has(field.key)) continue
    labels.push(shortLabel(field))
  }
  return labels
}

/** True only for jobs before Applied (Backlog or Prepare). */
export function shouldShowSavedAnswers(funnelStage: string | null | undefined): boolean {
  return funnelStage === 'backlog' || funnelStage === 'prepare'
}

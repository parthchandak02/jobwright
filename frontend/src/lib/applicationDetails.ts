import type { AnswerFieldSpec, AnswerSectionId, ApplicationAnswers } from '@/lib/api'

export const SECTION_ORDER: { id: AnswerSectionId; title: string }[] = [
  { id: 'contact', title: 'Contact and address' },
  { id: 'education', title: 'Education' },
  { id: 'eligibility', title: 'Work eligibility' },
  { id: 'pay_start', title: 'Pay and start date' },
  { id: 'diversity', title: 'Diversity questions (optional)' },
  { id: 'other', title: 'Other questions forms asked' },
]

/** Fields shown elsewhere on About you (one place per value). */
export const SHOWN_ABOVE = new Set(['phone'])

/** The small label next to a saved answer. */
export function sourceLabel(source: string | undefined | null): string {
  if (source === 'resume') return 'From your resume'
  if (source === 'told_claude' || source === 'connector') return 'You told Claude'
  return 'You entered'
}

/** Answer fields by section, in display order (sections the server names win; empty ones stay). */
export function fieldsBySection(data: Pick<ApplicationAnswers, 'fields' | 'sections'>) {
  const order = data.sections?.length ? data.sections : SECTION_ORDER
  return order.map((s) => ({
    ...s,
    fields: data.fields.filter((f: AnswerFieldSpec) => (f.section ?? 'other') === s.id && !SHOWN_ABOVE.has(f.key)),
  }))
}

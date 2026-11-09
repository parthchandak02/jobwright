import type { AnswerFieldSpec, AnswerSectionId, ApplicationAnswers } from '@/lib/api'

export const SECTION_ORDER: { id: AnswerSectionId; title: string }[] = [
  { id: 'contact', title: 'Contact and address' },
  { id: 'education', title: 'Education' },
  { id: 'eligibility', title: 'Work eligibility' },
  { id: 'experience', title: 'Experience' },
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

/**
 * Short on-screen names for the standard questions. The full wording (what Claude and the forms
 * see) stays in the spec and opens from the ⓘ.
 */
export const SHORT_LABELS: Record<string, string> = {
  work_authorized: 'Can work in the job’s country',
  requires_sponsorship: 'Need visa sponsorship',
  criminal_record: 'Criminal conviction',
  background_check: 'OK with a background check',
  age_18_plus: '18 or older',
  certify: 'Tick “I certify”',
  privacy_consent: 'Accept privacy and data consent',
  years_experience: 'Years of experience',
  years_leadership: 'Years in leadership',
  years_managing: 'Years managing people',
  largest_team: 'Largest team managed',
  salary_expectation: 'Pay expectation',
  start_date: 'Earliest start',
  relocation: 'Will relocate',
  previously_worked_here: 'Worked there before',
  onsite: 'Can work on-site',
  currently_in_country: 'In the job’s country now',
  willing_to_travel: 'Travel',
  eeo_gender: 'Gender',
  eeo_race: 'Race or ethnicity',
  eeo_hispanic: 'Hispanic or Latino',
  eeo_veteran: 'Veteran status',
  eeo_disability: 'Disability',
  eeo_lgbtq: 'Sexual orientation',
  state: 'State',
  postal_code: 'ZIP',
  linkedin_url: 'LinkedIn',
  github_url: 'GitHub',
  portfolio_url: 'Website',
  education_highest: 'Highest education',
  how_heard: 'How you heard',
  referral: 'Referred by an employee',
  pronouns: 'Pronouns',
  preferred_name: 'Preferred name',
}

export function shortLabel(spec: Pick<AnswerFieldSpec, 'key' | 'label'>): string {
  return SHORT_LABELS[spec.key] ?? spec.label
}

/** A yes / no question: shown as one row with the answer on the right. */
export function isYesNo(spec: Pick<AnswerFieldSpec, 'choices'>): boolean {
  return spec.choices.length === 2 && spec.choices.includes('Yes') && spec.choices.includes('No')
}

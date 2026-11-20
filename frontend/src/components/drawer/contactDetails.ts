/** Explicit allowlist of personal keys safe to surface for one-tap copy in the job drawer. */
export const CONTACT_DETAIL_ALLOWLIST = [
  { key: 'full_name', label: 'Full name' },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Phone' },
  { key: 'city', label: 'City' },
  { key: 'province_state', label: 'State' },
  { key: 'country', label: 'Country' },
  { key: 'postal_code', label: 'ZIP' },
  { key: 'linkedin_url', label: 'LinkedIn' },
  { key: 'github_url', label: 'GitHub' },
] as const

export type ContactDetailKey = (typeof CONTACT_DETAIL_ALLOWLIST)[number]['key']

export type ContactDetailItem = {
  key: ContactDetailKey
  label: string
  value: string
}

/** Extract non-empty allowlisted contact fields; password and unknown keys are never returned. */
export function pickContactDetails(personal: Record<string, unknown> | null | undefined): ContactDetailItem[] {
  if (!personal || typeof personal !== 'object') return []
  const items: ContactDetailItem[] = []
  for (const field of CONTACT_DETAIL_ALLOWLIST) {
    if (!Object.prototype.hasOwnProperty.call(personal, field.key)) continue
    const raw = personal[field.key]
    if (typeof raw !== 'string') continue
    const value = raw.trim()
    if (!value) continue
    items.push({ key: field.key, label: field.label, value })
  }
  return items
}

/** True only for jobs before Applied (Backlog or Prepare). */
export function shouldShowContactDetails(funnelStage: string | null | undefined): boolean {
  return funnelStage === 'backlog' || funnelStage === 'prepare'
}

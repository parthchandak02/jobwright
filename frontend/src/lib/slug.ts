/** Stable id for a rule label: lowercase, `_`-joined, max 32 chars ("rule" if empty). */
export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 32) || 'rule'
}

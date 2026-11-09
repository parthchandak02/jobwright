/**
 * Short pay for cards and rows: "$165,000 - $190,000" → "$165k-190k", "$45/hr" stays as is.
 * Anything it can't read comes back unchanged, so nothing is ever made up.
 */
export function compactPay(raw: string | null | undefined): string {
  const text = (raw || '').trim()
  if (!text) return ''
  if (/hour|\/hr|\bhr\b|per h/i.test(text)) return text
  const nums = [...text.matchAll(/([$£€₹])?\s?(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d+)?\s?(k|K)?/g)]
  if (!nums.length || nums.length > 2) return text
  const symbol = nums.find((m) => m[1])?.[1] ?? ''
  const short = (m: RegExpMatchArray) => {
    const n = Number(m[2].replace(/,/g, ''))
    if (!Number.isFinite(n) || n < 1000) return null
    const k = n / 1000
    return `${Number.isInteger(k) ? k : k.toFixed(1)}k`
  }
  const parts = nums.map(short)
  if (parts.some((p) => p == null)) return text
  return `${symbol}${parts.join('-')}`
}

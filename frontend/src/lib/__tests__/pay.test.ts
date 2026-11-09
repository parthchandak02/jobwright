import { describe, expect, it } from 'vitest'
import { compactPay } from '@/lib/pay'

describe('compactPay', () => {
  it('shortens a yearly range', () => {
    expect(compactPay('$165,000 - $190,000')).toBe('$165k-190k')
    expect(compactPay('$150000 - $180000')).toBe('$150k-180k')
  })
  it('shortens one figure and keeps halves', () => {
    expect(compactPay('$92,500')).toBe('$92.5k')
  })
  it('leaves hourly and unreadable pay alone', () => {
    expect(compactPay('$45 - $60 / hour')).toBe('$45 - $60 / hour')
    expect(compactPay('Competitive')).toBe('Competitive')
    expect(compactPay('')).toBe('')
  })
})

import type { CSSProperties } from 'react'

export type ScoreLevel = 'strong' | 'partial' | 'weak' | 'none'

export function scoreLevel(score: number | null | undefined): ScoreLevel {
  if (score == null) return 'none'
  if (score >= 7) return 'strong'
  if (score >= 5) return 'partial'
  return 'weak'
}

export const SCORE_LABEL: Record<ScoreLevel, string> = {
  strong: 'Strong match',
  partial: 'Partial match',
  weak: 'Weak match',
  none: 'Not scored yet',
}

export const SCORE_SHORT: Record<ScoreLevel, string> = {
  strong: 'Strong',
  partial: 'Partial',
  weak: 'Weak',
  none: 'New',
}

const SCORE_TONE: Record<ScoreLevel, string | null> = {
  strong: '--success',
  partial: '--warning',
  weak: null,
  none: null,
}

export function scoreToneStyle(score: number | null | undefined): CSSProperties | undefined {
  const tone = SCORE_TONE[scoreLevel(score)]
  return tone ? ({ '--tone': `var(${tone})` } as CSSProperties) : undefined
}

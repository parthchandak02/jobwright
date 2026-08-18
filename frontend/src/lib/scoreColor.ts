import type { CSSProperties } from 'react'

const MIN = 1
const MAX = 10

/**
 * Red → amber → lime → emerald-teal. Hues skip lane tokens (~50, 100, 150, 255, 330)
 * so score color stays readable on every kanban lane tint.
 */
export function scoreHue(score: number): number {
  const t = (Math.min(MAX, Math.max(MIN, score)) - MIN) / (MAX - MIN)
  if (t < 0.4) return 27 + (55 - 27) * (t / 0.4)
  if (t < 0.75) return 55 + (125 - 55) * ((t - 0.4) / 0.35)
  return 125 + (158 - 125) * ((t - 0.75) / 0.25)
}

export function scoreChroma(score: number): number {
  const t = (Math.min(MAX, Math.max(MIN, score)) - MIN) / (MAX - MIN)
  return 0.17 + 0.06 * Math.sin(t * Math.PI)
}

export type ScoreColors = {
  accent: string
  ring: string
  soft: string
}

export function getScoreColors(score: number): ScoreColors {
  const hue = scoreHue(score)
  const chroma = scoreChroma(score)
  const c = chroma.toFixed(3)
  const h = hue.toFixed(1)
  return {
    accent: `oklch(0.74 ${c} ${h})`,
    ring: `oklch(0.58 ${c} ${h} / 0.55)`,
    soft: `oklch(0.58 ${c} ${h} / 0.14)`,
  }
}

export function scoreBadgeStyle(score: number | null | undefined): CSSProperties | undefined {
  if (score == null) return undefined
  const { accent, ring, soft } = getScoreColors(score)
  return {
    color: accent,
    backgroundColor: 'color-mix(in oklch, var(--card) 94%, transparent)',
    boxShadow: `0 0 0 2px var(--background), 0 1px 4px oklch(0.2 0.02 260 / 0.35), inset 0 0 0 1px ${ring}`,
    ['--score-soft' as string]: soft,
  }
}

export function scoreTextStyle(score: number | null | undefined): CSSProperties | undefined {
  if (score == null) return undefined
  const { accent } = getScoreColors(score)
  return { color: accent }
}

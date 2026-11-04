import { describe, expect, it } from 'vitest'

import css from '../../index.css?raw'

// Guards WCAG AA (4.5:1) for tinted text built from the colour tokens in index.css:
// the `tone-tint` chip recipe (stage chips, Badge variants, score pills, alert chips)
// and `.lane-label`, in both themes. Colours are mixed in OKLab exactly like
// `color-mix(in oklab, ...)`, converted to sRGB (clipped) and measured with the WCAG formula.

type Lab = [number, number, number]
type Tokens = Record<string, string>

function block(selector: string): Tokens {
  const start = css.indexOf(`\n${selector} {`)
  if (start < 0) throw new Error(`missing ${selector} block`)
  const body = css.slice(start, css.indexOf('\n}', start))
  const out: Tokens = {}
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}

const LIGHT = block(':root')
const DARK = { ...LIGHT, ...block('.dark') }

function resolve(t: Tokens, value: string): string {
  let v = value.trim()
  for (let i = 0; i < 10 && v.startsWith('var('); i++) {
    const name = v.slice(4, -1).split(',')[0].trim().replace(/^--/, '')
    v = t[name]
    if (v == null) throw new Error(`unresolved token --${name}`)
  }
  return v
}

function oklab(t: Tokens, value: string): Lab {
  const v = resolve(t, value)
  const m = v.match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/)
  if (!m) throw new Error(`expected an opaque oklch() colour, got ${v}`)
  const [L, C, h] = m.slice(1).map(Number)
  const r = (h * Math.PI) / 180
  return [L, C * Math.cos(r), C * Math.sin(r)]
}

const mix = (a: Lab, b: Lab, p: number): Lab => [0, 1, 2].map((i) => a[i] * p + b[i] * (1 - p)) as Lab

function luminance([L, a, b]: Lab): number {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((x) => Math.min(1, Math.max(0, x)))
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
}

function contrast(x: Lab, y: Lab): number {
  const [hi, lo] = [luminance(x), luminance(y)].sort((p, q) => q - p)
  return (hi + 0.05) / (lo + 0.05)
}

function pct(t: Tokens, value: string): number {
  const v = resolve(t, value)
  if (!/^[\d.]+%$/.test(v)) throw new Error(`expected a percentage, got ${v}`)
  return parseFloat(v) / 100
}

/** Percentages used by `@utility tone-tint` for the fill and the text. */
function recipe() {
  const start = css.indexOf('@utility tone-tint {')
  const body = css.slice(start, css.indexOf('}', start))
  const bg = body.match(/background-color:\s*color-mix\(in oklab, var\(--tone[^)]*\)\)\s*([^,]+),\s*var\(--surface\)\)/)
  const text = body.match(/\bcolor:\s*color-mix\(in oklab, var\(--tone[^)]*\)\)\s*([^,]+),\s*var\(--foreground\)\)/)
  if (!bg || !text) throw new Error('tone-tint recipe changed shape; update tokenContrast.test.ts')
  return { bg: bg[1], text: text[1] }
}

const TONES = [
  'stage-backlog',
  'stage-prepare',
  'stage-applied',
  'stage-in-progress',
  'stage-offer',
  'stage-closed',
  'success',
  'warning',
  'destructive',
  'primary',
  'tone-neutral',
]
const THEMES: [string, Tokens][] = [
  ['light', LIGHT],
  ['dark', DARK],
]
const AA = 4.5

describe('tone-tint text contrast (WCAG AA)', () => {
  const r = recipe()
  for (const [theme, t] of THEMES) {
    for (const tone of TONES) {
      it(`${theme} ${tone}`, () => {
        const c = oklab(t, `var(--${tone})`)
        const surface = oklab(t, 'var(--surface)')
        const bg = mix(c, surface, pct(t, r.bg))
        const text = mix(c, oklab(t, 'var(--foreground)'), pct(t, r.text))
        expect(contrast(text, bg)).toBeGreaterThanOrEqual(AA)
      })
    }
  }
})

describe('.lane-label contrast (WCAG AA)', () => {
  const lanes = TONES.filter((n) => n.startsWith('stage-'))
  const labelMix = css.match(/\.lane-label \{\s*color:\s*color-mix\(in oklab, var\(--lane\)\s*([^,]+),\s*var\(--foreground\)\)/)
  it('recipe is parseable', () => expect(labelMix).not.toBeNull())
  for (const [theme, t] of THEMES) {
    for (const lane of lanes) {
      it(`${theme} ${lane} on lane card, board and sidebar`, () => {
        const c = oklab(t, `var(--${lane})`)
        const text = mix(c, oklab(t, 'var(--foreground)'), pct(t, labelMix![1]))
        // Lane card hover (10%) is the darkest/lightest tint the label sits on.
        const backgrounds = [mix(c, oklab(t, 'var(--surface)'), 0.1), oklab(t, 'var(--background)'), oklab(t, 'var(--sidebar)')]
        for (const bg of backgrounds) expect(contrast(text, bg)).toBeGreaterThanOrEqual(AA)
      })
    }
  }
})

import { describe, expect, it } from 'vitest'

import {
  clampPanelWidth,
  defaultPanelWidth,
  PANEL_MAX,
  PANEL_MIN,
  PANEL_TWO_COLUMN_MIN,
  panelMax,
  parseStoredWidth,
} from '@/lib/jobPanel'

describe('panel width', () => {
  it('takes about 45% of the window by default', () => {
    expect(defaultPanelWidth(1440)).toBe(648)
    expect(defaultPanelWidth(1920)).toBe(864)
  })

  it('opens single-column at 1440 and two-column at 1920', () => {
    expect(defaultPanelWidth(1440)).toBeLessThan(PANEL_TWO_COLUMN_MIN)
    expect(defaultPanelWidth(1920)).toBeGreaterThanOrEqual(PANEL_TWO_COLUMN_MIN)
  })

  it('never goes below the minimum or above the maximum', () => {
    expect(clampPanelWidth(100, 1440)).toBe(PANEL_MIN)
    expect(clampPanelWidth(5000, 2560)).toBe(PANEL_MAX)
    expect(defaultPanelWidth(1280)).toBe(576)
  })

  it('leaves the board room on smaller windows', () => {
    expect(panelMax(1280)).toBe(584)
    expect(clampPanelWidth(900, 1280)).toBe(584)
    expect(panelMax(1440)).toBe(744)
    // Tiny windows still get a usable panel.
    expect(panelMax(1000)).toBe(PANEL_MIN)
  })

  it('falls back to the default for nonsense', () => {
    expect(clampPanelWidth(Number.NaN, 1440)).toBe(648)
  })
})

describe('parseStoredWidth', () => {
  it.each([
    [null, null],
    ['', null],
    ['abc', null],
    ['-5', null],
    ['0', null],
    ['700', 700],
  ] as const)('%s -> %s', (raw, want) => {
    expect(parseStoredWidth(raw)).toBe(want)
  })
})

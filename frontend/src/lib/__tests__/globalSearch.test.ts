import { describe, expect, it } from 'vitest'
import { highlight, isFindShortcut, matchPages } from '@/lib/globalSearch'

const key = (k: string, mods: Partial<Record<'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey', boolean>> = {}) => ({
  key: k,
  metaKey: false,
  ctrlKey: false,
  altKey: false,
  shiftKey: false,
  ...mods,
})

describe('isFindShortcut', () => {
  it('accepts ⌘F and Ctrl+F', () => {
    expect(isFindShortcut(key('f', { metaKey: true }))).toBe(true)
    expect(isFindShortcut(key('F', { ctrlKey: true }))).toBe(true)
  })
  it('ignores plain F and other combos', () => {
    expect(isFindShortcut(key('f'))).toBe(false)
    expect(isFindShortcut(key('f', { metaKey: true, shiftKey: true }))).toBe(false)
    expect(isFindShortcut(key('f', { ctrlKey: true, altKey: true }))).toBe(false)
    expect(isFindShortcut(key('g', { metaKey: true }))).toBe(false)
  })
})

describe('matchPages', () => {
  it('finds settings tabs by name and keyword', () => {
    expect(matchPages('resume', false).map((p) => p.label)).toEqual(['Documents'])
    expect(matchPages('whatsapp', false)[0].label).toBe('Daily list')
  })
  it('puts name matches before keyword matches', () => {
    expect(matchPages('applied', false)[0].label).toBe('Applied')
  })
  it('hides Admin from non-admins', () => {
    expect(matchPages('admin', false)).toEqual([])
    expect(matchPages('admin', true)[0].label).toBe('Admin')
  })
  it('returns nothing for an empty query', () => {
    expect(matchPages('  ', true)).toEqual([])
  })
})

describe('highlight', () => {
  it('marks every word, case-insensitively', () => {
    expect(highlight('Data Analyst at Data Co', 'data co')).toEqual([
      { text: 'Data', match: true },
      { text: ' Analyst at ', match: false },
      { text: 'Data', match: true },
      { text: ' ', match: false },
      { text: 'Co', match: true },
    ])
  })
  it('does not mark single letters', () => {
    expect(highlight('Data', 'a')).toEqual([{ text: 'Data', match: false }])
  })
  it('returns the text as is without a query', () => {
    expect(highlight('Designer', '')).toEqual([{ text: 'Designer', match: false }])
  })
})

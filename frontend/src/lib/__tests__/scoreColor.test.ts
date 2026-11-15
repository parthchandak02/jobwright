import { describe, expect, it } from 'vitest'

import { SCORE_LABEL, SCORE_SHORT, scoreLevel, scoreToneStyle } from '@/lib/scoreColor'

describe('scoreLevel', () => {
  it.each([
    [null, 'none'],
    [undefined, 'none'],
    [0, 'weak'],
    [4, 'weak'],
    [5, 'partial'],
    [6, 'partial'],
    [7, 'strong'],
    [10, 'strong'],
  ] as const)('%s -> %s', (score, level) => {
    expect(scoreLevel(score)).toBe(level)
  })
})

describe('labels', () => {
  it('has a label for every level', () => {
    for (const level of ['strong', 'partial', 'weak', 'none'] as const) {
      expect(SCORE_LABEL[level]).toBeTruthy()
      expect(SCORE_SHORT[level]).toBeTruthy()
    }
  })
})

describe('scoreToneStyle', () => {
  it('uses success for strong and warning for partial', () => {
    expect(scoreToneStyle(9)).toEqual({ '--tone': 'var(--success)' })
    expect(scoreToneStyle(5)).toEqual({ '--tone': 'var(--warning)' })
  })

  it('uses neutral for weak and no tone when unscored', () => {
    expect(scoreToneStyle(2)).toEqual({ '--tone': 'var(--tone-neutral)' })
    expect(scoreToneStyle(null)).toBeUndefined()
  })
})

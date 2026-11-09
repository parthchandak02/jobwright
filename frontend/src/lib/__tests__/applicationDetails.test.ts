import { describe, expect, it } from 'vitest'
import type { AnswerFieldSpec } from '@/lib/api'
import { fieldsBySection, sourceLabel } from '@/lib/applicationDetails'

const f = (key: string, section?: AnswerFieldSpec['section']): AnswerFieldSpec => ({
  key, label: key, category: 'common', attestation: false, required: true, hint: '', choices: [], section,
})

describe('sourceLabel', () => {
  it('names where a value came from', () => {
    expect(sourceLabel('resume')).toBe('From your resume')
    expect(sourceLabel('told_claude')).toBe('You told Claude')
    expect(sourceLabel('connector')).toBe('You told Claude')
    expect(sourceLabel('settings')).toBe('You entered')
    expect(sourceLabel(undefined)).toBe('You entered')
  })
})

describe('fieldsBySection', () => {
  it('groups fields in section order, leaves out phone (shown above) and files unknown ones under other', () => {
    const groups = fieldsBySection({
      fields: [f('phone', 'contact'), f('city', 'contact'), f('salary_expectation', 'pay_start'), f('mystery')],
    })
    expect(groups.map((g) => [g.id, g.fields.map((x) => x.key)])).toEqual([
      ['contact', ['city']],
      ['education', []],
      ['eligibility', []],
      ['experience', []],
      ['pay_start', ['salary_expectation']],
      ['diversity', []],
      ['other', ['mystery']],
    ])
  })
})

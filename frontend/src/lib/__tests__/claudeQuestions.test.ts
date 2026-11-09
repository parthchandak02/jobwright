import { describe, expect, it } from 'vitest'
import type { PendingInput } from '@/lib/api'
import { answerControl, questionGroups } from '@/lib/claudeQuestions'

const q = (over: Partial<PendingInput>): PendingInput => ({
  id: 'abcdefgh', kind: 'answer', prompt: 'Desired pay', company: 'Example Co', job_id: 'aaaaaaaaaaaa',
  status: 'open', created_at: '2026-11-08T10:00:00Z', expires_at: null, resolved_at: null, resolved_by: null,
  choices: [], asked_by: 'connector', ...over,
})

describe('questionGroups', () => {
  it('groups open answer questions by job and keeps their order', () => {
    const groups = questionGroups([
      q({ id: 'a1' }),
      q({ id: 'b1', job_id: 'bbbbbbbbbbbb', company: 'Other Co' }),
      q({ id: 'a2', prompt: 'Date available' }),
    ])
    expect(groups.map((g) => [g.company, g.questions.map((x) => x.id)])).toEqual([
      ['Example Co', ['a1', 'a2']],
      ['Other Co', ['b1']],
    ])
  })
  it('leaves out codes, CAPTCHAs and closed questions', () => {
    expect(questionGroups([q({ kind: 'email_code' }), q({ kind: 'captcha' }), q({ status: 'resolved' })])).toEqual([])
  })
  it('names a question with no job', () => {
    expect(questionGroups([q({ job_id: null, company: null })])[0].company).toBe('An application')
  })
})

describe('answerControl', () => {
  it('uses buttons for a few choices, a list for many and a text box for none', () => {
    expect(answerControl(['Yes', 'No'])).toBe('buttons')
    expect(answerControl(['0-2', '3-5', '6-9', '10+'])).toBe('select')
    expect(answerControl([])).toBe('text')
    expect(answerControl(undefined)).toBe('text')
    expect(answerControl(['  '])).toBe('text')
  })
})

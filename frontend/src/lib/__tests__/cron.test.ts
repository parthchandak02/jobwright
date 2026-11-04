import { describe, expect, it } from 'vitest'

import { cronDays, cronToTime, isSimpleTimeCron, withCronTime } from '@/lib/cron'

describe('cronToTime', () => {
  it.each([
    ['0 7 * * *', '07:00'],
    ['30 18 * * *', '18:30'],
    ['5 9 * * 1-5', '09:05'],
    [undefined, '07:00'],
    ['', '07:00'],
  ])('%s -> %s', (cron, time) => {
    expect(cronToTime(cron)).toBe(time)
  })

  it.each(['0 */3 * * 1-5', '0 6,12 * * *', '*/15 9 * * *', '0 7 * *', '0 99 * * *', 'nonsense'])(
    'custom schedule %s -> null',
    (cron) => {
      expect(cronToTime(cron)).toBeNull()
      expect(isSimpleTimeCron(cron)).toBe(false)
    },
  )
})

describe('withCronTime', () => {
  it('replaces only minute and hour', () => {
    expect(withCronTime('0 7 * * *', '08:45')).toBe('45 8 * * *')
    expect(withCronTime('15 6 * * 1-5', '19:05')).toBe('5 19 * * 1-5')
    expect(withCronTime('0 7 1 */2 *', '07:30')).toBe('30 7 1 */2 *')
  })

  it('uses the default schedule when none is set', () => {
    expect(withCronTime(undefined, '09:00')).toBe('0 9 * * *')
  })

  it('refuses custom schedules and bad times', () => {
    expect(withCronTime('0 */3 * * 1-5', '08:00')).toBeNull()
    expect(withCronTime('0 6,12 * * *', '08:00')).toBeNull()
    expect(withCronTime('0 7 * * *', '')).toBeNull()
    expect(withCronTime('0 7 * * *', '25:00')).toBeNull()
  })
})

describe('cronDays', () => {
  it.each([
    ['0 7 * * *', 'Every day'],
    ['0 7 * * 1-5', 'Weekdays'],
    ['0 7 * * 0,6', 'Weekends'],
    ['0 7 * * 1,3', null],
    ['0 7 1 * *', null],
  ])('%s -> %s', (cron, days) => {
    expect(cronDays(cron)).toBe(days)
  })
})

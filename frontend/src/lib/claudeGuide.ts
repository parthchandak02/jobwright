import type { ConnectorStatus } from '@/lib/api'

/** Settings → Claude guided setup: step order, status, the copy-ready prompts and the times shown. */

export type GuideStepId = 'connect' | 'answers' | 'chrome' | 'daily'

export type GuideStep = { id: GuideStepId; done: boolean }

export type GuideFlags = { chrome: boolean; daily: boolean }

export const GUIDE_ORDER: GuideStepId[] = ['connect', 'answers', 'chrome', 'daily']

/**
 * Which steps are done. Connect and answers come from the server; Chrome and the daily task can't be
 * seen from here, so the person ticks them (kept in localStorage). When jobwright's own server
 * applies for the profile, the daily Claude task isn't needed.
 */
export function guideSteps(data: Pick<ConnectorStatus, 'clients' | 'missing_answers' | 'apply_via'>, flags: GuideFlags): GuideStep[] {
  const done: Record<GuideStepId, boolean> = {
    connect: data.clients.length > 0,
    answers: (data.missing_answers ?? 0) === 0,
    chrome: flags.chrome,
    daily: flags.daily || data.apply_via === 'server',
  }
  return GUIDE_ORDER.map((id) => ({ id, done: done[id] }))
}

/** The first step not done yet (the one to emphasise), or null when everything is done. */
export function currentStep(steps: GuideStep[]): GuideStepId | null {
  return steps.find((s) => !s.done)?.id ?? null
}

/** "7:30 AM" in the viewer's time zone, from an ISO time with an offset. */
export function clockTime(iso: string | null | undefined, locale?: string): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString(locale ?? 'en-US', { hour: 'numeric', minute: '2-digit' })
}

/** The ISO time `minutes` after `iso` (the suggested start for the daily Claude task), or null. */
export function addMinutes(iso: string | null | undefined, minutes: number): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return new Date(d.getTime() + minutes * 60_000).toISOString()
}

/** "3 hours", "90 minutes", "1 hour". */
export function durationWords(minutes: number): string {
  if (minutes > 0 && minutes % 60 === 0) {
    const h = minutes / 60
    return `${h} ${h === 1 ? 'hour' : 'hours'}`
  }
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
}

// Minutes after the skip window closes before the Claude task starts, so every pick's time has passed.
export const DAILY_TASK_BUFFER_MINUTES = 15

export const ANSWERS_PROMPT = 'Help me fill in my jobwright application answers. Ask me one question at a time.'

export const DAILY_PROMPT =
  'Open jobwright and look at today’s picks. For each pick whose apply time has passed, apply with Claude in ' +
  'Chrome and follow jobwright’s instructions. Don’t ask me anything while you work: if a job needs me (a code, ' +
  'a CAPTCHA, an answer I haven’t saved, or an account), leave it for me and move on. When you’re done, tell ' +
  'me what you applied to and what still needs me.'

/** Short prompts in jobwright's voice; each maps to tools the connector has (see connector/tools.py). */
export const THINGS_TO_ASK = [
  'What’s new in jobwright today?',
  'Show today’s jobwright picks and why each one fits me.',
  'Apply to my top jobwright pick with Claude in Chrome. Stop before you submit so I can check it.',
  'Tailor my resume for my best jobwright match and save it to jobwright.',
  'Which jobs have I applied to in jobwright?',
  'Skip today’s jobwright picks.',
]

export const CHROME_WEB_STORE_URL = 'https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn'

const flagKey = (userId: string, flag: keyof GuideFlags) => `jobwright-claude-guide:${userId}:${flag}`

export function readGuideFlags(userId: string | null | undefined): GuideFlags {
  const read = (flag: keyof GuideFlags) => {
    if (!userId) return false
    try {
      return localStorage.getItem(flagKey(userId, flag)) === '1'
    } catch {
      return false
    }
  }
  return { chrome: read('chrome'), daily: read('daily') }
}

export function writeGuideFlag(userId: string | null | undefined, flag: keyof GuideFlags, on: boolean) {
  if (!userId) return
  try {
    if (on) localStorage.setItem(flagKey(userId, flag), '1')
    else localStorage.removeItem(flagKey(userId, flag))
  } catch {
    /* storage unavailable */
  }
}

const cardKey = (userId: string) => `jobwright-claude-card-dismissed:${userId}`

export function isClaudeCardDismissed(userId: string | null | undefined): boolean {
  if (!userId) return false
  try {
    return localStorage.getItem(cardKey(userId)) === '1'
  } catch {
    return false
  }
}

export function dismissClaudeCard(userId: string | null | undefined) {
  if (!userId) return
  try {
    localStorage.setItem(cardKey(userId), '1')
  } catch {
    /* storage unavailable */
  }
}

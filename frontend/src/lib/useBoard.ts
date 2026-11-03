import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  apiFetch,
  BoardResponse,
  getJob,
  JobCard,
  moveJob,
  previewNotify,
  Profile,
  reorderLane,
} from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/** What to refetch. The board is the default; profile and the WhatsApp preview only when asked. */
export type RefreshWhat = { board?: boolean; profile?: boolean; notify?: boolean }

type Kind = 'board' | 'profile' | 'notify'

export type MoveOptions = {
  outcome?: string
  reasons?: string[]
  close_reason?: string
  /** Index in the target lane (0 = top). */
  position?: number
}

/** Rapid refresh calls inside this window become one request per kind. */
const COALESCE_MS = 40

function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError'
}

/** Recompute totals after a local change (closed keeps its server total, adjusted by the caller). */
function withCounts(board: BoardResponse): BoardResponse {
  const counts: Record<string, number> = {}
  for (const stage of board.stages) counts[stage] = (board.columns[stage] || []).length
  if (board.closed_total != null) counts.closed = board.closed_total
  return {
    ...board,
    total: Object.values(board.columns).reduce((n, cards) => n + cards.length, 0),
    stage_counts: counts,
  }
}

/** Put `card` in `toStage` at `position` (default top), removing it from wherever it was. */
export function placeCard(board: BoardResponse, card: JobCard, toStage: string, position = 0): BoardResponse {
  let fromStage: string | undefined
  const columns: Record<string, JobCard[]> = {}
  for (const stage of board.stages) {
    const cards = board.columns[stage] || []
    if (!fromStage && cards.some((j) => j.url === card.url)) fromStage = stage
    columns[stage] = cards.filter((j) => j.url !== card.url)
  }
  const target = columns[toStage] || (columns[toStage] = [])
  target.splice(Math.max(0, Math.min(position, target.length)), 0, card)
  let closed = board.closed_total
  if (closed != null && fromStage !== toStage) {
    if (toStage === 'closed') closed += 1
    else if (fromStage === 'closed') closed = Math.max(0, closed - 1)
  }
  return withCounts({ ...board, columns, closed_total: closed })
}

/** Swap in a fresh copy of a card; if its lane changed, it moves to the top of the new lane. */
export function replaceCard(board: BoardResponse, card: JobCard): BoardResponse {
  for (const stage of board.stages) {
    const cards = board.columns[stage] || []
    const idx = cards.findIndex((j) => j.url === card.url)
    if (idx === -1) continue
    if (stage === card.funnel_stage || !board.stages.includes(card.funnel_stage)) {
      const next = [...cards]
      next[idx] = card
      return { ...board, columns: { ...board.columns, [stage]: next } }
    }
    return placeCard(board, card, card.funnel_stage)
  }
  return board
}

/**
 * Board data for the dashboard shell: the board, the profile and the WhatsApp
 * pending count, with light refreshes.
 *
 * `refresh()` refetches only the board. Calls within a few ms are coalesced,
 * and a newer request aborts an older one of the same kind so a slow, stale
 * response can never overwrite fresh data.
 */
export function useBoard() {
  const [board, setBoardState] = useState<BoardResponse | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [pendingNotify, setPendingNotify] = useState(0)
  const [loading, setLoading] = useState(true)

  const boardRef = useRef<BoardResponse | null>(null)
  const queued = useRef<Set<Kind>>(new Set())
  const waiters = useRef<Array<() => void>>([])
  const timer = useRef<number | undefined>(undefined)
  const controllers = useRef<Partial<Record<Kind, AbortController>>>({})

  const setBoard = useCallback((next: BoardResponse | null) => {
    boardRef.current = next
    setBoardState(next)
  }, [])

  const updateBoard = useCallback(
    (fn: (b: BoardResponse) => BoardResponse) => {
      const cur = boardRef.current
      if (cur) setBoard(fn(cur))
    },
    [setBoard],
  )

  const fetchKind = useCallback(
    async (kind: Kind) => {
      controllers.current[kind]?.abort()
      const ctrl = new AbortController()
      controllers.current[kind] = ctrl
      const { signal } = ctrl
      try {
        if (kind === 'board') {
          const b = await apiFetch<BoardResponse>('/board', { signal })
          if (!signal.aborted) setBoard(b)
        } else if (kind === 'profile') {
          const p = await apiFetch<Profile>('/profile', { signal })
          if (!signal.aborted) setProfile(p)
        } else {
          const r = await apiFetch<Awaited<ReturnType<typeof previewNotify>>>('/notify/preview', { signal })
          if (!signal.aborted) setPendingNotify(r.skipped ? 0 : r.jobs.length)
        }
      } catch (e) {
        if (isAbort(e) || signal.aborted) return
        if (kind === 'notify') setPendingNotify(0)
        else toast.error(errorMessage(e))
      } finally {
        if (kind === 'board' && !signal.aborted) setLoading(false)
        if (controllers.current[kind] === ctrl) delete controllers.current[kind]
      }
    },
    [setBoard],
  )

  const refresh = useCallback(
    (what: RefreshWhat = {}): Promise<void> => {
      if (what.board ?? true) queued.current.add('board')
      if (what.profile) queued.current.add('profile')
      if (what.notify) queued.current.add('notify')
      return new Promise<void>((resolve) => {
        waiters.current.push(resolve)
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
          const kinds = [...queued.current]
          const done = waiters.current
          queued.current = new Set()
          waiters.current = []
          void Promise.all(kinds.map(fetchKind)).then(() => done.forEach((r) => r()))
        }, COALESCE_MS)
      })
    },
    [fetchKind],
  )

  useEffect(() => {
    void refresh({ board: true, profile: true, notify: true })
    const ctrls = controllers.current
    return () => {
      window.clearTimeout(timer.current)
      Object.values(ctrls).forEach((c) => c?.abort())
    }
  }, [refresh])

  /** Refetch one card (e.g. after a score save) and patch it in place: no board reload. */
  const refreshCard = useCallback(
    async (job: Pick<JobCard, 'job_id' | 'url'>) => {
      try {
        const fresh = await getJob(job)
        updateBoard((b) => replaceCard(b, fresh))
      } catch {
        void refresh()
      }
    },
    [refresh, updateBoard],
  )

  /** Optimistic lane change; the server's copy of the card replaces the guess. */
  const moveCard = useCallback(
    async (job: JobCard, toStage: string, opts: MoveOptions = {}) => {
      const prev = boardRef.current
      if (!prev) return
      const guess: JobCard = { ...job, funnel_stage: toStage, ...(opts.outcome ? { outcome: opts.outcome } : {}) }
      setBoard(placeCard(prev, guess, toStage, opts.position ?? 0))
      try {
        const res = await moveJob(job, toStage, opts)
        updateBoard((b) => replaceCard(b, res.job))
      } catch (e) {
        setBoard(prev)
        toast.error(errorMessage(e))
      }
    },
    [setBoard, updateBoard],
  )

  /** Patch server copies of several cards in (e.g. after a bulk action): no board reload. */
  const applyCards = useCallback(
    (cards: JobCard[]) => updateBoard((b) => [...cards].reverse().reduce(replaceCard, b)),
    [updateBoard],
  )

  /** Persist the order of one lane as shown in `next`; on failure go back to `revert`. */
  const saveLaneOrder = useCallback(
    async (stage: string, next: BoardResponse, revert: BoardResponse | null) => {
      const ids = (next.columns[stage] || []).map((j) => j.job_id).filter(Boolean)
      try {
        await reorderLane(stage, ids)
      } catch (e) {
        if (revert) setBoard(revert)
        toast.error(errorMessage(e))
      }
    },
    [setBoard],
  )

  return {
    board,
    setBoard,
    profile,
    pendingNotify,
    loading,
    refresh,
    refreshCard,
    moveCard,
    applyCards,
    saveLaneOrder,
  }
}

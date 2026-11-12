import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Loader2, Search } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { ScoreBadge } from '@/components/ScoreBadge'
import { STAGE_LABELS, STAGE_TONE } from '@/lib/api'
import { highlight, isFindShortcut, matchPages, searchJobs, type JobHit, type PageHit } from '@/lib/globalSearch'
import { useMe } from '@/lib/me'
import { cn } from '@/lib/utils'

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const FIND_KEY = IS_MAC ? '⌘F' : 'Ctrl+F'

type Item = { kind: 'page'; page: PageHit } | { kind: 'job'; job: JobHit }

function Marked({ text, q }: { text: string; q: string }) {
  return (
    <>
      {highlight(text, q).map((part, i) =>
        part.match ? (
          <mark key={i} className="rounded-sm bg-primary/15 text-inherit">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}

function StageDot({ stage }: { stage: string }) {
  const tone = STAGE_TONE[stage] || STAGE_TONE.backlog
  return (
    <span className="inline-flex items-center gap-1.5 text-caption text-muted-foreground">
      <span aria-hidden className="size-2 rounded-full" style={{ background: `var(${tone})` }} />
      {STAGE_LABELS[stage] || stage}
    </span>
  )
}

function Row({
  id,
  active,
  onPick,
  onHover,
  children,
}: {
  id: string
  active: boolean
  onPick: () => void
  onHover: () => void
  children: ReactNode
}) {
  return (
    // The input keeps focus and drives the list (aria-activedescendant); rows are clicked or tapped.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events
    <li
      id={id}
      role="option"
      aria-selected={active}
      onClick={onPick}
      onPointerMove={onHover}
      className={cn(
        'flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 py-2',
        active && 'bg-surface-muted',
      )}
    >
      {children}
    </li>
  )
}

/**
 * ⌘F / Ctrl+F anywhere in the app opens a search over every job (closed ones too: title, company,
 * place, notes, description) and the app's pages. Pressing it again while open hands over to the
 * browser's own find-in-page.
 */
export function GlobalSearch() {
  const navigate = useNavigate()
  const { me } = useMe()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [jobs, setJobs] = useState<JobHit[]>([])
  const [total, setTotal] = useState(0)
  const [searchedFor, setSearchedFor] = useState('')
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const openRef = useRef(open)
  openRef.current = open

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!isFindShortcut(e)) return
      if (openRef.current) {
        // Second press: let the browser's find bar open on the page underneath.
        setOpen(false)
        return
      }
      e.preventDefault()
      const selected = window.getSelection()?.toString().trim() ?? ''
      if (selected && selected.length <= 80 && !selected.includes('\n')) setQuery(selected)
      setOpen(true)
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  const q = query.trim()

  useEffect(() => {
    if (!open) return
    if (!q) {
      setJobs([])
      setTotal(0)
      setSearchedFor('')
      setLoading(false)
      setFailed(false)
      return
    }
    const ctrl = new AbortController()
    setLoading(true)
    const t = window.setTimeout(() => {
      searchJobs(q, ctrl.signal)
        .then((res) => {
          setJobs(res.results)
          setTotal(res.total)
          setSearchedFor(q)
          setFailed(false)
          setLoading(false)
        })
        .catch((e: unknown) => {
          if ((e as { name?: string })?.name === 'AbortError') return
          setFailed(true)
          setLoading(false)
        })
    }, 120)
    return () => {
      window.clearTimeout(t)
      ctrl.abort()
    }
  }, [q, open])

  const pages = useMemo(() => matchPages(q, Boolean(me?.is_admin)), [q, me?.is_admin])
  const items: Item[] = useMemo(
    () => [...pages.map((page) => ({ kind: 'page' as const, page })), ...jobs.map((job) => ({ kind: 'job' as const, job }))],
    [pages, jobs],
  )
  useEffect(() => setActive(0), [items])

  function pick(item: Item | undefined) {
    if (!item) return
    setOpen(false)
    navigate(item.kind === 'page' ? item.page.to : `/jobs/${item.job.job_id}`)
  }

  function onInputKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!items.length) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      const next = (active + step + items.length) % items.length
      setActive(next)
      document.getElementById(`gs-item-${next}`)?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(items[active])
    }
  }

  const nothing = q && !loading && !failed && searchedFor === q && items.length === 0

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        size="picker"
        showCloseButton={false}
        aria-describedby={undefined}
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          inputRef.current?.focus()
          inputRef.current?.select()
        }}
        className="gap-0 overflow-hidden p-0 max-sm:px-0 max-sm:pt-5 sm:top-[12vh] sm:translate-y-0"
      >
        <DialogTitle className="sr-only">Search everything</DialogTitle>
        <div className="flex items-center gap-2 border-b px-4">
          {loading ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden />
          ) : (
            <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search jobs, companies, notes, pages"
            aria-label="Search everything"
            role="combobox"
            aria-expanded={items.length > 0}
            aria-controls="gs-list"
            aria-activedescendant={items.length ? `gs-item-${active}` : undefined}
            autoComplete="off"
            spellCheck={false}
            className="h-13 min-w-0 flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground"
          />
          <kbd className="hidden rounded border px-1.5 py-0.5 text-micro text-muted-foreground sm:inline">Esc</kbd>
        </div>

        <div className="max-h-[min(60vh,32rem)] overflow-y-auto overscroll-contain p-2 max-sm:max-h-[60dvh]">
          {failed ? (
            <p className="px-3 py-6 text-center text-caption text-muted-foreground">Couldn’t search. Try again.</p>
          ) : nothing ? (
            <p className="px-3 py-6 text-center text-caption text-muted-foreground">No matches</p>
          ) : !q ? (
            <p className="px-3 py-6 text-center text-caption text-muted-foreground">
              Every job, closed ones too
            </p>
          ) : null}
          {items.length ? (
            <ul id="gs-list" role="listbox" aria-label="Results" className="flex flex-col gap-0.5">
              {items.map((item, i) => {
                const key = item.kind === 'page' ? `p:${item.page.to}` : `j:${item.job.job_id}`
                const common = { id: `gs-item-${i}`, active: i === active, onPick: () => pick(item), onHover: () => setActive(i) }
                if (item.kind === 'page') {
                  return (
                    <Row key={key} {...common}>
                      <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1 truncate text-body">
                        {item.page.group ? <span className="text-muted-foreground">{item.page.group} › </span> : null}
                        <Marked text={item.page.label} q={q} />
                      </span>
                    </Row>
                  )
                }
                const job = item.job
                const sub = [job.company, job.location].filter(Boolean).join(' · ')
                return (
                  <Row key={key} {...common}>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-body font-medium">
                        <Marked text={job.title || 'Untitled job'} q={q} />
                      </div>
                      {sub ? (
                        <div className="truncate text-caption text-muted-foreground">
                          <Marked text={sub} q={q} />
                        </div>
                      ) : null}
                      {job.snippet ? (
                        <div className="line-clamp-2 text-caption text-muted-foreground">
                          <Marked text={job.snippet} q={q} />
                        </div>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <ScoreBadge score={job.fit_score} label="none" />
                      <StageDot stage={job.funnel_stage} />
                    </div>
                  </Row>
                )
              })}
            </ul>
          ) : null}
          {total > jobs.length && searchedFor === q ? (
            <p className="px-3 pt-2 pb-1 text-caption text-muted-foreground">
              Best {jobs.length} of {total}. Add a word to narrow it.
            </p>
          ) : null}
        </div>

        <div className="hidden items-center justify-between border-t px-4 py-2 text-micro text-muted-foreground sm:flex">
          <span>
            <kbd className="font-sans">↑↓</kbd> move · <kbd className="font-sans">↵</kbd> open
          </span>
          <span>
            <kbd className="font-sans">{FIND_KEY}</kbd> again: find on this page
          </span>
        </div>
      </DialogContent>
    </Dialog>
  )
}

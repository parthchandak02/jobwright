import { useState } from 'react'
import { Layers, Plus, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { AutoSearchControls } from '@/components/AutoSearchControls'
import { ViewModeTabs, type ViewMode } from '@/components/ViewModeTabs'
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { cn } from '@/lib/utils'

function BoardSearch({
  value,
  onChange,
  autoFocus,
  className,
}: {
  value: string
  onChange: (v: string) => void
  autoFocus?: boolean
  className?: string
}) {
  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input
        type="search"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onChange('')
        }}
        placeholder="Search title, company or place"
        className="pl-9 md:h-9"
        aria-label="Search jobs"
      />
    </div>
  )
}

type Props = {
  title: string
  /** Jobs in view; hidden until the board has loaded. */
  count: number | null
  view: ViewMode
  onViewChange: (view: ViewMode) => void
  search: string
  onSearchChange: (q: string) => void
  pendingNotify: number
  onOpenWhatsApp: () => void
  onAddJob: () => void
  onRunDone: () => void
  /** Unrated Backlog jobs; shows a "Review N" link to /review when above 0. */
  reviewCount?: number
}

/** Sticky board header: title + count, view tabs, search, Auto Search, WhatsApp and Add job. */
export function BoardHeader({
  title,
  count,
  view,
  onViewChange,
  search,
  onSearchChange,
  pendingNotify,
  onOpenWhatsApp,
  onAddJob,
  onRunDone,
  reviewCount = 0,
}: Props) {
  // Phone: search opens over the header. Starts open when a shared link carries a search.
  const [searchOpen, setSearchOpen] = useState(() => Boolean(search))

  return (
    <header
      className={cn(
        'board-head sticky top-0 z-20',
        APP_SHELL_HEADER,
        'max-md:h-14 max-md:flex-nowrap max-md:gap-1 max-md:px-2 max-md:py-0',
      )}
    >
      {searchOpen ? (
        <div className="flex min-w-0 flex-1 items-center gap-1 md:hidden">
          <BoardSearch value={search} onChange={onSearchChange} autoFocus={!search} className="flex-1" />
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              onSearchChange('')
              setSearchOpen(false)
            }}
          >
            Cancel
          </Button>
        </div>
      ) : null}
      <div className={cn('flex min-w-0 flex-1 items-center gap-1 md:gap-4', searchOpen && 'max-md:hidden')}>
        <h1 className="board-head-title min-w-0 truncate text-heading text-foreground max-md:pl-2">
          {title}
          {count != null ? <span className="ml-2 font-normal text-muted-foreground tabular-nums">{count}</span> : null}
        </h1>
        <div className="max-md:hidden">
          <ViewModeTabs value={view} onChange={onViewChange} />
        </div>
        <BoardSearch value={search} onChange={onSearchChange} className="board-head-search w-64 max-md:hidden" />

        <div className="ml-auto flex shrink-0 items-center gap-0.5 md:gap-2">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="md:hidden"
            onClick={() => setSearchOpen(true)}
            aria-label="Open search"
          >
            <Search />
          </Button>

          {reviewCount > 0 ? (
            <>
              <Button asChild size="icon-sm" variant="ghost" className="md:hidden">
                <Link to="/review" aria-label={`Review ${reviewCount} Backlog jobs`}>
                  <Layers />
                </Link>
              </Button>
              <Button asChild size="sm" variant="secondary" className="max-md:hidden" title="Go through Backlog jobs one at a time">
                <Link to="/review">
                  <Layers /> <span className="board-head-label">Review</span> <Badge variant="secondary">{reviewCount}</Badge>
                </Link>
              </Button>
            </>
          ) : null}
          <AutoSearchControls onRunDone={onRunDone} />

          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="md:hidden"
            onClick={onOpenWhatsApp}
            aria-label={`Daily WhatsApp list${pendingNotify ? `, ${pendingNotify} waiting` : ''}`}
          >
            <WhatsAppIcon className="text-whatsapp" />
            {pendingNotify > 0 ? (
              <span className="absolute top-0 right-0 min-w-4 rounded-full bg-primary px-1 text-center text-micro leading-4 text-primary-foreground tabular-nums">
                {pendingNotify}
              </span>
            ) : null}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="max-md:hidden"
            onClick={onOpenWhatsApp}
            title="Daily WhatsApp list"
          >
            <WhatsAppIcon className="text-whatsapp" />
            <span className="board-head-label">WhatsApp</span>
            {pendingNotify > 0 ? <Badge variant="secondary">{pendingNotify}</Badge> : null}
          </Button>

          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="md:hidden"
            onClick={onAddJob}
            aria-label="Add a job"
          >
            <Plus />
          </Button>
          <Button size="sm" variant="secondary" className="max-md:hidden" onClick={onAddJob}>
            <Plus />
            <span className="board-head-label">Add job</span>
          </Button>
        </div>
      </div>
    </header>
  )
}

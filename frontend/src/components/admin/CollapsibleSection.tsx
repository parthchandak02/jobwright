import { useId, useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  title: string
  summary?: ReactNode
  defaultOpen?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
  id?: string
  children: ReactNode
}

/** Section header (heading size) that expands its content; collapsed by default. */
export function CollapsibleSection({ title, summary, defaultOpen = false, open: openProp, onOpenChange, id, children }: Props) {
  const [openState, setOpenState] = useState(defaultOpen)
  const open = openProp ?? openState
  const panelId = useId()

  function toggle() {
    setOpenState(!open)
    onOpenChange?.(!open)
  }

  return (
    <section id={id} className="mt-section scroll-mt-20 border-t pt-3">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={toggle}
          className="-mx-2 flex w-[calc(100%+1rem)] min-w-0 items-start gap-3 rounded-md px-2 py-2 text-left transition-colors duration-(--dur-1) hover:bg-surface-muted"
        >
          <span className="min-w-0 flex-1">
            <span className="block text-heading text-foreground">{title}</span>
            {summary ? <span className="mt-0.5 block truncate text-caption text-muted-foreground">{summary}</span> : null}
          </span>
          <ChevronRight
            className={cn(
              'mt-1 size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-2) ease-out',
              open && 'rotate-90',
            )}
            aria-hidden
          />
        </button>
      </h2>
      {open ? (
        <div id={panelId} className="pt-4">
          {children}
        </div>
      ) : null}
    </section>
  )
}

import { useId, useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  title: string
  summary?: ReactNode
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  children: ReactNode
}

export function CollapsibleSection({ title, summary, defaultOpen = false, onOpenChange, children }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <section className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          setOpen(!open)
          onOpenChange?.(!open)
        }}
        className="flex w-full min-w-0 items-center gap-2 rounded-md py-1 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <ChevronRight
          className={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-200', open && 'rotate-90')}
          aria-hidden
        />
        <h2 className="shrink-0 text-sm font-semibold">{title}</h2>
        {summary ? <span className="min-w-0 truncate text-xs text-muted-foreground">{summary}</span> : null}
      </button>
      {open ? <div id={id}>{children}</div> : null}
    </section>
  )
}

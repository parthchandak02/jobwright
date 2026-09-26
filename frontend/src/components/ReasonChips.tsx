import { cn } from '@/lib/utils'

type Props = {
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  tone?: 'negative' | 'positive'
  className?: string
}

/** Multi-select reason pills (toggle buttons, keyboard accessible). */
export function ReasonChips({ options, selected, onChange, tone = 'negative', className }: Props) {
  const on = new Set(selected)
  return (
    <div className={cn('flex flex-wrap gap-1.5', className)} role="group" aria-label="Reasons">
      {options.map((opt) => {
        const active = on.has(opt)
        return (
          <button
            key={opt}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? selected.filter((s) => s !== opt) : [...selected, opt])}
            className={cn(
              'rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
              active
                ? tone === 'negative'
                  ? 'border-destructive/50 bg-destructive/10 text-destructive'
                  : 'border-primary/50 bg-primary/10 text-primary'
                : 'border-border/70 text-muted-foreground hover:bg-accent/60 hover:text-foreground',
            )}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}

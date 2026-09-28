import type { CSSProperties } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  tone?: 'negative' | 'positive'
  className?: string
}

export function ReasonChips({ options, selected, onChange, tone = 'negative', className }: Props) {
  const on = new Set(selected)
  const toneStyle = { '--tone': tone === 'negative' ? 'var(--destructive)' : 'var(--primary)' } as CSSProperties
  return (
    <div className={cn('flex flex-wrap gap-2', className)} role="group" aria-label="Reasons">
      {options.map((opt) => {
        const active = on.has(opt)
        return (
          <button
            key={opt}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? selected.filter((s) => s !== opt) : [...selected, opt])}
            style={active ? toneStyle : undefined}
            className={cn(
              'touch-target relative inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-caption transition-colors duration-(--dur-1) ease-out md:h-8',
              active ? 'tone-tint font-medium' : 'border-border bg-surface text-foreground hover:bg-surface-muted',
            )}
          >
            {active ? <Check className="size-3.5" aria-hidden /> : null}
            {opt}
          </button>
        )
      })}
    </div>
  )
}

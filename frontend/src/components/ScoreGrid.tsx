import { useRef, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'

export const SCORE_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const

type Props = {
  value: number | null
  onChange: (score: number | null) => void
  /** Accessible name of the radiogroup. */
  label: string
  disabled?: boolean
  /** Clicking the picked score again clears it (optional scores). */
  allowDeselect?: boolean
  /** `comfortable`: 5 x 2 grid (score editor). `compact`: one row (rating panel). */
  density?: 'comfortable' | 'compact'
  className?: string
}

/**
 * A 1-10 score picker with the ARIA radiogroup keyboard model: one tab stop
 * (roving tabindex on the picked score, else the first), arrow keys move and
 * pick, Home/End jump to 1/10, Space picks the focused score.
 */
export function ScoreGrid({
  value,
  onChange,
  label,
  disabled,
  allowDeselect,
  density = 'comfortable',
  className,
}: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const tabStop = value != null && value >= 1 && value <= 10 ? value : SCORE_VALUES[0]

  function pickAt(index: number) {
    const i = (index + SCORE_VALUES.length) % SCORE_VALUES.length
    refs.current[i]?.focus()
    onChange(SCORE_VALUES[i])
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        pickAt(index + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        pickAt(index - 1)
        break
      case 'Home':
        pickAt(0)
        break
      case 'End':
        pickAt(SCORE_VALUES.length - 1)
        break
      case ' ':
        onChange(SCORE_VALUES[index])
        break
      default:
        return
    }
    e.preventDefault()
  }

  const compact = density === 'compact'
  return (
    <div
      role="radiogroup"
      aria-label={label}
      aria-disabled={disabled || undefined}
      className={cn(compact ? 'grid grid-cols-10 gap-1 md:flex md:gap-1.5' : 'grid grid-cols-5 gap-1.5', className)}
    >
      {SCORE_VALUES.map((n, i) => {
        const checked = value === n
        return (
          <button
            key={n}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={n === tabStop ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(allowDeselect && checked ? null : n)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              'rounded-md border tabular-nums transition-colors duration-(--dur-1) disabled:opacity-50',
              compact ? 'h-10 text-caption md:h-8 md:w-8' : 'h-10 text-label md:h-9',
              checked
                ? cn('border-primary bg-accent text-accent-foreground', compact && 'font-medium')
                : cn(
                    'border-border bg-surface',
                    compact ? 'text-muted-foreground hover:text-foreground' : 'text-foreground hover:bg-surface-muted',
                  ),
            )}
          >
            {n}
          </button>
        )
      })}
    </div>
  )
}

import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export const BOARDS = [
  { id: 'indeed', label: 'Indeed' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'google', label: 'Google' },
  { id: 'glassdoor', label: 'Glassdoor' },
  { id: 'zip_recruiter', label: 'ZipRecruiter' },
] as const

/** Boards discovery uses when none are saved (`discovery/jobspy.py`). */
export const DEFAULT_BOARDS: readonly string[] = ['indeed', 'linkedin', 'zip_recruiter']

type Props = {
  value: string[]
  onChange: (next: string[]) => void
  className?: string
  id?: string
  'aria-describedby'?: string
}

export function isDefaultBoards(value: string[]): boolean {
  return value.length === 0
}

export function BoardToggles({ value, onChange, className, id, 'aria-describedby': describedBy }: Props) {
  const effective = value.length ? value : DEFAULT_BOARDS
  const selected = new Set(effective)

  const toggle = (boardId: string) => {
    if (selected.has(boardId)) {
      if (selected.size === 1) return
      onChange(effective.filter((b) => b !== boardId))
      return
    }
    onChange([...effective, boardId])
  }

  return (
    <div
      id={id}
      role="group"
      aria-describedby={describedBy}
      className={cn('flex flex-wrap gap-2', className)}
    >
      {BOARDS.map((board) => {
        const on = selected.has(board.id)
        const last = on && selected.size === 1
        return (
          <button
            key={board.id}
            type="button"
            role="checkbox"
            aria-checked={on}
            aria-disabled={last || undefined}
            title={last ? 'Keep at least one board on' : undefined}
            onClick={() => toggle(board.id)}
            className={cn(
              'inline-flex h-11 items-center gap-2 rounded-full border pr-4 pl-3 text-label transition-[color,background-color,border-color] duration-(--dur-1) ease-out md:h-9 md:pr-3.5 md:pl-2.5',
              on
                ? 'border-primary/35 bg-accent text-accent-foreground hover:border-primary/55'
                : 'border-border-strong bg-surface text-muted-foreground hover:bg-surface-muted hover:text-foreground',
              last && 'cursor-default',
            )}
          >
            <span
              aria-hidden
              className={cn(
                'inline-flex size-4 items-center justify-center rounded-full border transition-colors duration-(--dur-1)',
                on ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong bg-surface',
              )}
            >
              {on ? <Check className="size-3" strokeWidth={3} /> : null}
            </span>
            {board.label}
          </button>
        )
      })}
    </div>
  )
}

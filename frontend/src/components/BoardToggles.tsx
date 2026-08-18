import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const BOARDS = [
  { id: 'indeed', label: 'Indeed' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'google', label: 'Google' },
  { id: 'glassdoor', label: 'Glassdoor' },
  { id: 'zip_recruiter', label: 'ZipRecruiter' },
] as const

type Props = {
  value: string[]
  onChange: (next: string[]) => void
  className?: string
}

export function BoardToggles({ value, onChange, className }: Props) {
  const selected = new Set(value)

  const toggle = (boardId: string) => {
    if (selected.has(boardId)) {
      onChange(value.filter((id) => id !== boardId))
      return
    }
    onChange([...value, boardId])
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {BOARDS.map((board) => {
        const isSelected = selected.has(board.id)
        return (
          <Button
            key={board.id}
            type="button"
            size="sm"
            variant={isSelected ? 'default' : 'outline'}
            aria-pressed={isSelected}
            onClick={() => toggle(board.id)}
          >
            {board.label}
          </Button>
        )
      })}
    </div>
  )
}

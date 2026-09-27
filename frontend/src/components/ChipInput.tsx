import { Plus } from 'lucide-react'
import { useCallback, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from 'react'
import { ValueChip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type Props = {
  values: string[]
  onChange: (next: string[]) => void
  /** Short instruction such as "Add a job title". Avoid example values; they read as real entries. */
  placeholder?: string
  addLabel?: string
  className?: string
  /** Semantic tint only (e.g. `--destructive` for blocked phrases). Neutral by default. */
  tone?: string
  /** Show only the first N chips with a "Show all" toggle. */
  collapseAfter?: number
  /** Optional per-chip control (e.g. a DropdownMenu trigger), rendered inside the chip before remove. */
  renderActions?: (value: string, index: number) => ReactNode
  disabled?: boolean
  id?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
}

function isDuplicate(values: string[], candidate: string): boolean {
  const lower = candidate.toLowerCase()
  return values.some((v) => v.toLowerCase() === lower)
}

export function ChipInput({
  values,
  onChange,
  placeholder,
  addLabel,
  className,
  tone,
  collapseAfter,
  renderActions,
  disabled,
  id,
  'aria-describedby': describedBy,
  'aria-invalid': invalid,
}: Props) {
  const [draft, setDraft] = useState('')
  const [expanded, setExpanded] = useState(false)

  const addValues = useCallback(
    (raws: string[]) => {
      const next = [...values]
      for (const raw of raws) {
        const v = raw.trim()
        if (v && !isDuplicate(next, v)) next.push(v)
      }
      if (next.length !== values.length) onChange(next)
      setDraft('')
    },
    [onChange, values],
  )

  const removeAt = useCallback(
    (index: number) => {
      onChange(values.filter((_, i) => i !== index))
    },
    [onChange, values],
  )

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addValues([draft])
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text')
    if (!/[,\n]/.test(text)) return
    e.preventDefault()
    addValues(text.split(/[,\n]/))
  }

  const collapsed = collapseAfter != null && !expanded && values.length > collapseAfter
  const shown = collapsed ? values.slice(0, collapseAfter) : values
  const label = addLabel ?? placeholder ?? 'Add item'

  return (
    <div className={cn('space-y-2', className)}>
      {values.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {shown.map((value, index) => (
            <ValueChip
              key={`${value}-${index}`}
              tone={tone}
              onRemove={disabled ? undefined : () => removeAt(index)}
              trailing={renderActions?.(value, index)}
            >
              {value}
            </ValueChip>
          ))}
          {collapseAfter != null && values.length > collapseAfter ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="touch-target relative rounded-md px-1.5 text-micro text-primary hover:underline"
              aria-expanded={expanded}
            >
              {expanded ? 'Show less' : `Show all ${values.length}`}
            </button>
          ) : null}
        </div>
      )}
      <div className="relative">
        <Plus
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground"
          aria-hidden
        />
        <Input
          id={id}
          type="text"
          value={draft}
          disabled={disabled}
          placeholder={placeholder ?? 'Add…'}
          aria-label={label}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          enterKeyHint="done"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          className="pl-9"
        />
      </div>
    </div>
  )
}

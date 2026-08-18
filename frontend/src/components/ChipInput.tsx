import { useCallback, useState, type KeyboardEvent } from 'react'
import { Chip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type Props = {
  values: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  addLabel?: string
  className?: string
  /** CSS custom-property token, same as Chip `tone` (e.g. --stage-offer). */
  tone?: string
}

function normalizeValue(raw: string): string {
  return raw.trim()
}

function isDuplicate(values: string[], candidate: string): boolean {
  const lower = candidate.toLowerCase()
  return values.some((v) => v.toLowerCase() === lower)
}

export function ChipInput({ values, onChange, placeholder, addLabel, className, tone }: Props) {
  const [draft, setDraft] = useState('')

  const addValue = useCallback(
    (raw: string) => {
      const next = normalizeValue(raw)
      if (!next || isDuplicate(values, next)) return
      onChange([...values, next])
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
    if (e.key === 'Enter') {
      e.preventDefault()
      addValue(draft)
      return
    }
    if (e.key === ',') {
      e.preventDefault()
      addValue(draft)
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      {values.length > 0 && (
        <div className="job-card-chips">
          {values.map((value, index) => (
            <Chip key={`${value}-${index}`} tone={tone} onRemove={() => removeAt(index)}>
              {value}
            </Chip>
          ))}
        </div>
      )}
      <Input
        type="text"
        value={draft}
        placeholder={placeholder}
        aria-label={addLabel ?? placeholder ?? 'Add item'}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
      />
    </div>
  )
}

import { useState, type KeyboardEvent } from 'react'
import { Plus } from 'lucide-react'
import { ValueChip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type LocationEntry = { location: string; remote: boolean }

type Props = {
  locations: LocationEntry[]
  onChange: (next: LocationEntry[]) => void
  className?: string
  placeholder?: string
  id?: string
  'aria-describedby'?: string
}

function isRemotePlace(name: string): boolean {
  return name.trim().toLowerCase() === 'remote'
}

export function LocationChipInput({
  locations,
  onChange,
  className,
  placeholder = 'Add a city, or type Remote',
  id,
  'aria-describedby': describedBy,
}: Props) {
  const [draft, setDraft] = useState('')

  function add() {
    const location = draft.trim()
    if (!location) return
    if (!locations.some((l) => l.location.toLowerCase() === location.toLowerCase())) {
      onChange([...locations, { location, remote: isRemotePlace(location) }])
    }
    setDraft('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      {locations.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {locations.map((entry, index) => (
            <ValueChip
              key={`${entry.location}-${index}`}
              onRemove={() => onChange(locations.filter((_, i) => i !== index))}
              removeLabel={entry.location}
            >
              {entry.location}
            </ValueChip>
          ))}
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
          placeholder={placeholder}
          aria-label="Add a place"
          aria-describedby={describedBy}
          enterKeyHint="done"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={add}
          className="pl-9"
        />
      </div>
    </div>
  )
}

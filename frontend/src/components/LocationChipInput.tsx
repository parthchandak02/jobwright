import { useCallback, useState, type KeyboardEvent } from 'react'
import { Chip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type LocationEntry = { location: string; remote: boolean }

type Props = {
  locations: LocationEntry[]
  onChange: (next: LocationEntry[]) => void
  className?: string
}

function normalizeLocation(raw: string): string {
  return raw.trim()
}

function isRemotePlace(name: string): boolean {
  return name.trim().toLowerCase() === 'remote'
}

function isDuplicate(locations: LocationEntry[], candidate: string): boolean {
  const lower = candidate.toLowerCase()
  return locations.some((l) => l.location.toLowerCase() === lower)
}

export function LocationChipInput({ locations, onChange, className }: Props) {
  const [draft, setDraft] = useState('')

  const addLocation = useCallback(
    (raw: string) => {
      const location = normalizeLocation(raw)
      if (!location || isDuplicate(locations, location)) return
      onChange([...locations, { location, remote: isRemotePlace(location) }])
      setDraft('')
    },
    [locations, onChange],
  )

  const removeAt = useCallback(
    (index: number) => {
      onChange(locations.filter((_, i) => i !== index))
    },
    [onChange, locations],
  )

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addLocation(draft)
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      {locations.length > 0 && (
        <div className="job-card-chips">
          {locations.map((entry, index) => (
            <Chip
              key={`${entry.location}-${index}`}
              tone="--stage-applied"
              onRemove={() => removeAt(index)}
              removeLabel={entry.location}
            >
              {entry.location}
            </Chip>
          ))}
        </div>
      )}
      <Input
        type="text"
        value={draft}
        placeholder="San Francisco, CA"
        aria-label="Add location"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
      />
    </div>
  )
}

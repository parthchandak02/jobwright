import { useState, type KeyboardEvent } from 'react'
import { Plus } from 'lucide-react'
import { ValueChip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import type { LocationEntry, RemoteScope } from '@/lib/api'
import { cn } from '@/lib/utils'

export type { LocationEntry }

type Props = {
  locations: LocationEntry[]
  onChange: (next: LocationEntry[]) => void
  className?: string
  placeholder?: string
  id?: string
  'aria-describedby'?: string
}

type RemoteChoice = 'off' | RemoteScope

const REMOTE_OPTIONS: { value: RemoteChoice; label: string }[] = [
  { value: 'off', label: 'No' },
  { value: 'us', label: 'US only' },
  { value: 'any', label: 'All countries' },
]

function isRemotePlace(name: string): boolean {
  return name.trim().toLowerCase() === 'remote'
}

/** City chips plus one "Remote jobs" choice; remote always carries a scope (US only or all countries). */
export function LocationChipInput({
  locations,
  onChange,
  className,
  placeholder = 'Add a city or region',
  id,
  'aria-describedby': describedBy,
}: Props) {
  const [draft, setDraft] = useState('')
  const places = locations.filter((l) => !l.remote)
  const remote = locations.find((l) => l.remote)
  const choice: RemoteChoice = remote ? (remote.remote_scope ?? 'us') : 'off'

  function setRemote(next: RemoteChoice) {
    onChange(next === 'off' ? places : [...places, { location: 'Remote', remote: true, remote_scope: next }])
  }

  function add() {
    const location = draft.trim()
    setDraft('')
    if (!location) return
    if (isRemotePlace(location)) {
      if (!remote) setRemote('us')
      return
    }
    if (!places.some((l) => l.location.toLowerCase() === location.toLowerCase())) {
      onChange([...places, { location, remote: false }, ...(remote ? [remote] : [])])
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="space-y-2">
        {places.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {places.map((entry, index) => (
              <ValueChip
                key={`${entry.location}-${index}`}
                onRemove={() => onChange(locations.filter((l) => l !== entry))}
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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-label text-muted-foreground">Remote jobs</span>
        <Segmented value={choice} onValueChange={setRemote} options={REMOTE_OPTIONS} aria-label="Remote jobs" />
      </div>
    </div>
  )
}

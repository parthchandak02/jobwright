import { ArrowLeft, Loader2, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { Profile, SettingsData } from '@/lib/api'
import { MutedList } from './parts'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  settings: SettingsData | null | undefined
  profile: Profile | null | undefined
  starting: boolean
  onEdit: (what: 'search' | 'daily' | 'letters') => void
  onBack: () => void
  onBoard: () => void
  onStart: () => void
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}

function clock(schedule?: string): string | null {
  const [m, h] = (schedule || '').split(' ')
  if (!/^\d+$/.test(m ?? '') || !/^\d+$/.test(h ?? '')) return null
  const d = new Date()
  d.setHours(Number(h), Number(m), 0, 0)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function Row({ label, value, onEdit }: { label: string; value: ReactNode; onEdit?: () => void }) {
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-caption text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-body text-foreground">{value}</p>
      </div>
      {onEdit ? (
        <Button type="button" size="sm" variant="ghost" className="-my-1 -mr-2 text-primary" onClick={onEdit}>
          Edit
        </Button>
      ) : null}
    </li>
  )
}

export function StepFinish({ settings, profile, starting, onEdit, onBack, onBoard, onStart }: Props) {
  const loading = settings === undefined || profile === undefined
  const queries = settings?.searches.queries ?? []
  const daily = queries.filter((q) => (q.tier || 1) <= 1).length
  const weekly = queries.length - daily
  const places = (settings?.searches.locations ?? []).map((l) => l.location)
  const letters = settings?.cover_letter_examples.length ?? 0
  const time = profile?.schedule_label || clock(profile?.schedule)
  const chat = profile?.whatsapp_chat_name || (profile?.whatsapp_target ? 'Connected chat' : null)

  return (
    <WelcomeStep
      title="You’re all set"
      description="Here’s what we set up. You can change any of it later in Settings."
      back={
        <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={starting}>
          <ArrowLeft /> Back
        </Button>
      }
      actions={
        <>
          <Button type="button" size="sm" variant="ghost" className="max-md:hidden" onClick={onBoard} disabled={starting}>
            Go to my board
          </Button>
          <Button type="button" size="sm" onClick={onStart} disabled={starting}>
            {starting ? <Loader2 className="animate-spin" /> : <Search />}
            Find my first jobs
          </Button>
        </>
      }
    >
      {loading ? (
        <div className="space-y-2" aria-label="Loading your summary">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <MutedList>
          {settings ? (
            <Row
              label="Job titles"
              value={
                queries.length
                  ? `${plural(daily, 'title')} every morning${weekly ? `, ${weekly} more weekly` : ''}`
                  : 'None yet'
              }
              onEdit={() => onEdit('search')}
            />
          ) : null}
          {settings ? (
            <Row
              label="Where"
              value={places.length ? places.join(' · ') : 'Anywhere'}
              onEdit={() => onEdit('search')}
            />
          ) : null}
          {profile ? (
            <Row
              label="Daily list"
              value={
                [time ? `${time}${profile.timezone ? ` ${profile.timezone}` : ''}` : null, chat ?? 'Chat not connected yet']
                  .filter(Boolean)
                  .join(' · ')
              }
              onEdit={() => onEdit('daily')}
            />
          ) : null}
          {settings ? (
            <Row
              label="Cover letters"
              value={letters ? plural(letters, 'letter') : 'None yet'}
              onEdit={() => onEdit('letters')}
            />
          ) : null}
        </MutedList>
      )}
      <p className="mt-6 text-body text-muted-foreground">
        Your first search takes 30 to 60 minutes, and new matches appear on your board as they’re found. After that,
        your daily list arrives once a day at the time you picked.
      </p>
      <Button type="button" variant="link" className="touch-target mt-2 h-auto px-0 md:hidden" onClick={onBoard} disabled={starting}>
        Go to my board without searching
      </Button>
    </WelcomeStep>
  )
}

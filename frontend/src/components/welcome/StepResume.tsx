import { useEffect, useState } from 'react'
import { ArrowRight, Check, Loader2 } from 'lucide-react'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { DraftHints } from '@/lib/api'
import { cn } from '@/lib/utils'
import { WelcomeStep } from './WelcomeShell'
import { Disclosure, DropZone } from './parts'

type Props = {
  file: File | null
  onFile: (f: File | null) => void
  hasResume: boolean
  hints: DraftHints
  onHints: (h: DraftHints) => void
  drafting: boolean
  onDraft: () => void
}

const STAGES: { label: string; from: number }[] = [
  { label: 'Reading your resume', from: 0 },
  { label: 'Picking job titles and places to search', from: 12 },
  { label: 'Writing how we judge fit', from: 30 },
]

function elapsedLabel(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function Drafting() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(t)
  }, [])
  const current = STAGES.reduce((acc, s, i) => (seconds >= s.from ? i : acc), 0)

  return (
    <WelcomeStep
      title="Drafting your search"
      description="This usually takes under a minute. Keep this page open; you’ll review everything next."
    >
      <ol className="space-y-4" aria-live="polite">
        {STAGES.map((s, i) => {
          const done = i < current
          const active = i === current
          return (
            <li key={s.label} className="flex items-center gap-3">
              <span
                className={cn(
                  'flex size-6 shrink-0 items-center justify-center rounded-full',
                  done && 'bg-primary text-primary-foreground',
                  active && 'bg-accent text-accent-foreground',
                  !done && !active && 'border border-border-strong',
                )}
                aria-hidden
              >
                {done ? <Check className="size-3.5" /> : active ? <Loader2 className="size-3.5 animate-spin" /> : null}
              </span>
              <span className={cn('text-body', done || active ? 'text-foreground' : 'text-muted-foreground')}>
                {s.label}
                <span className="sr-only">{done ? ' (done)' : active ? ' (in progress)' : ''}</span>
              </span>
            </li>
          )
        })}
      </ol>
      <p className="mt-8 text-caption text-muted-foreground tabular-nums">{elapsedLabel(seconds)} elapsed</p>
    </WelcomeStep>
  )
}

export function StepResume({ file, onFile, hasResume, hints, onHints, drafting, onDraft }: Props) {
  if (drafting) return <Drafting />
  const hintCount = Object.values(hints).filter((v) => v?.trim()).length
  const ready = Boolean(file) || hasResume

  return (
    <WelcomeStep
      title="Add your resume"
      description="We read it to draft your search: the jobs to look for, where, and what to skip. You’ll check everything before it’s saved."
      actions={
        <Button type="button" size="sm" disabled={!ready} onClick={onDraft}>
          Draft my search <ArrowRight />
        </Button>
      }
    >
      <DropZone
        onFiles={(files) => onFile(files[0] ?? null)}
        hasFile={ready}
        title={file ? file.name : hasResume ? 'Your resume is on file' : 'Choose your resume'}
        detail={
          file
            ? 'Ready. Choose again to use a different file.'
            : hasResume
              ? 'Continue with it, or choose a newer PDF.'
              : 'A PDF file. Drop it here or browse. Only you can see it.'
        }
      />

      <Disclosure
        className="mt-6"
        title="Add a few hints"
        summary={hintCount ? `${hintCount} added` : 'Optional'}
        defaultOpen={hintCount > 0}
      >
        <div className="space-y-field">
          <p className="text-caption text-muted-foreground">
            Useful when your resume doesn’t show where you want to go next.
          </p>
          <FormField label="Roles you want" hint="For example: program manager at an education nonprofit.">
            <Input
              value={hints.target_roles || ''}
              onChange={(e) => onHints({ ...hints, target_roles: e.target.value })}
              placeholder="Describe the roles you want"
            />
          </FormField>
          <FormField label="Where you want to work" hint="Cities, regions, or remote.">
            <Input
              value={hints.locations || ''}
              onChange={(e) => onHints({ ...hints, locations: e.target.value })}
              placeholder="Add places, separated by commas"
            />
          </FormField>
          <FormField label="Lowest yearly pay you’d accept" hint="In US dollars. Leave empty if you’re not sure.">
            <Input
              value={hints.min_salary || ''}
              inputMode="numeric"
              onChange={(e) => onHints({ ...hints, min_salary: e.target.value })}
              placeholder="Enter an amount"
            />
          </FormField>
          <FormField label="Jobs you never want to see" hint="For example: sales, fundraising, roles that need a license.">
            <Input
              value={hints.avoid || ''}
              onChange={(e) => onHints({ ...hints, avoid: e.target.value })}
              placeholder="Add kinds of work, separated by commas"
            />
          </FormField>
        </div>
      </Disclosure>
    </WelcomeStep>
  )
}

import type { FormEvent, ReactNode } from 'react'
import { BrandLogo } from '@/components/BrandLogo'
import { ActionBar } from '@/components/ActionBar'
import { cn } from '@/lib/utils'

export const PROGRESS_LABELS = ['About you', 'Resume', 'Your search', 'How we judge fit', 'Daily list', 'Cover letters']

type ShellProps = {
  /** Zero-based index into PROGRESS_LABELS; `PROGRESS_LABELS.length` means finished. */
  progress: number
  email?: string
  children: ReactNode
}

function Progress({ progress }: { progress: number }) {
  const total = PROGRESS_LABELS.length
  const done = progress >= total
  const label = done ? 'All set' : PROGRESS_LABELS[progress]
  return (
    <div className="mt-5 md:mt-8">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-label text-foreground" aria-live="polite">
          {label}
        </p>
        <p className="shrink-0 text-caption text-muted-foreground tabular-nums">
          {done ? `${total} of ${total} done` : `Step ${progress + 1} of ${total}`}
        </p>
      </div>
      <div
        role="progressbar"
        aria-label="Setup progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done ? total : progress + 1}
        aria-valuetext={done ? 'Setup complete' : `Step ${progress + 1} of ${total}: ${label}`}
        className="mt-2.5 flex gap-1"
      >
        {PROGRESS_LABELS.map((l, i) => (
          <span
            key={l}
            className={cn(
              'h-1 flex-1 rounded-full transition-colors duration-(--dur-3) ease-out',
              i <= progress || done ? 'bg-primary' : 'bg-border',
            )}
          />
        ))}
      </div>
    </div>
  )
}

/** Welcome page frame: brand row, progress, centred 560px column. No sidebar, no app menu. */
export function WelcomeShell({ progress, email, children }: ShellProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <div className="flex-1 px-page-x">
        <div className="mx-auto w-full max-w-welcome pt-5 md:pt-12">
          <div className="flex items-center gap-2.5">
            <BrandLogo className="size-7 text-foreground" />
            <span className="text-subheading text-foreground">jobwright</span>
          </div>
          <Progress progress={progress} />
          <div className="pt-6 pb-8 md:pt-8 md:pb-12">{children}</div>
        </div>
      </div>
      {email ? (
        <p className="px-page-x pb-[calc(1.5rem+var(--safe-bottom))] text-center text-caption text-muted-foreground">
          Signed in as {email}
        </p>
      ) : null}
    </div>
  )
}

type StepProps = {
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  /** Left side of the sticky footer (usually Back). */
  back?: ReactNode
  /** Right side of the sticky footer (the primary action, plus at most one more). */
  actions?: ReactNode
  onSubmit?: () => void
  className?: string
}

const FOOTER = cn(
  'md:bottom-0 md:mt-0',
  '[&_[role=region]>p]:-ml-2 [&_[role=region]>p]:overflow-visible',
  'md:[&_[role=region]]:rounded-t-none md:[&_[role=region]]:border-x-0 md:[&_[role=region]]:border-b-0 md:[&_[role=region]]:px-10 md:[&_[role=region]]:py-4 md:[&_[role=region]]:shadow-none',
)

/** One step: title block + content on a surface card (flat on phone) + sticky footer actions. */
export function WelcomeStep({ title, description, children, back, actions, onSubmit, className }: StepProps) {
  const body = (
    <section
      className={cn('md:rounded-lg md:border md:bg-surface', className)}
      aria-labelledby="welcome-step-title"
    >
      <div className="md:px-10 md:pt-9 md:pb-10">
        <header className={cn(children ? 'mb-8' : null)}>
          <h1 id="welcome-step-title" className="text-title text-foreground md:text-display">
            {title}
          </h1>
          {description ? <p className="mt-2 text-body text-muted-foreground">{description}</p> : null}
        </header>
        {children}
      </div>
      {back || actions ? (
        <ActionBar message={back ?? null} className={FOOTER}>
          {actions}
        </ActionBar>
      ) : null}
    </section>
  )
  if (!onSubmit) return body
  return (
    <form
      noValidate
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      {body}
    </form>
  )
}

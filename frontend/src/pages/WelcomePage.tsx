import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check, FileText, Loader2, Sparkles, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { BrandLogo } from '@/components/BrandLogo'
import { ChipInput } from '@/components/ChipInput'
import { CriteriaEditor } from '@/components/CriteriaEditor'
import { FormField } from '@/components/FormField'
import { LocationChipInput } from '@/components/LocationChipInput'
import { QueryChipInput } from '@/components/QueryChipInput'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  apiUpload,
  confirmSetup,
  createProfile,
  draftSetup,
  getOnboardingStatus,
  startRun,
  updateProfile,
  type DraftHints,
  type OnboardingDraft,
  type OnboardingStatus,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'

type Step = 'name' | 'resume' | 'review' | 'whatsapp' | 'letters' | 'done'

const STEPS: { id: Step; label: string }[] = [
  { id: 'name', label: 'You' },
  { id: 'resume', label: 'Resume' },
  { id: 'review', label: 'What to look for' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'letters', label: 'Cover letters' },
  { id: 'done', label: 'Start' },
]

function Progress({ step }: { step: Step }) {
  const idx = STEPS.findIndex((s) => s.id === step)
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" aria-label="Setup progress">
      {STEPS.map((s, i) => (
        <li key={s.id} className={cn('flex items-center gap-1.5', i <= idx ? 'text-foreground' : 'text-muted-foreground')}>
          <span
            className={cn(
              'flex size-5 items-center justify-center rounded-full border text-xs font-semibold',
              i < idx && 'border-primary bg-primary text-primary-foreground',
              i === idx && 'border-primary text-primary',
            )}
          >
            {i < idx ? <Check className="size-3" /> : i + 1}
          </span>
          {s.label}
        </li>
      ))}
    </ol>
  )
}

function Panel({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">{title}</h1>
        {lead ? <p className="text-sm text-muted-foreground">{lead}</p> : null}
      </header>
      {children}
    </section>
  )
}

function firstStepFor(status: OnboardingStatus | null): Step {
  if (!status?.has_profile) return 'name'
  const s = status.steps
  if (!s.resume) return 'resume'
  if (!s.profile || !s.searches) return 'resume'
  if (!s.whatsapp) return 'whatsapp'
  if (!s.cover_letters) return 'letters'
  return 'done'
}

export function WelcomePage() {
  const navigate = useNavigate()
  const { me, refresh } = useMe()
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [step, setStep] = useState<Step>('name')
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [hints, setHints] = useState<DraftHints>({})
  const [draft, setDraft] = useState<OnboardingDraft | null>(null)
  const [target, setTarget] = useState('')
  const [time, setTime] = useState('07:00')
  const [letters, setLetters] = useState<string[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const lettersRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void getOnboardingStatus()
      .then((s) => {
        setStatus(s)
        setStep(firstStepFor(s))
      })
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  async function doCreate() {
    if (!name.trim()) return
    setBusy(true)
    try {
      await createProfile(name.trim())
      await refresh()
      setStatus(await getOnboardingStatus())
      setStep('resume')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function doDraft() {
    if (!file && !status?.steps.resume) {
      toast.error('Add your resume as a PDF first.')
      return
    }
    setBusy(true)
    try {
      setDraft(await draftSetup(file, hints))
      setStep('review')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function doConfirm() {
    if (!draft) return
    if (!draft.searches.queries.length) {
      toast.error('Add at least one search keyword.')
      return
    }
    setBusy(true)
    try {
      setStatus(await confirmSetup(draft))
      setStep('whatsapp')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function doWhatsApp() {
    if (!target) {
      toast.error('Pick a chat for your daily list.')
      return
    }
    const [h, m] = time.split(':').map(Number)
    setBusy(true)
    try {
      const res = await updateProfile({ schedule: `${m} ${h} * * *`, whatsapp_target: target })
      if (res.cron_error) toast.info(`Saved. Daily schedule note: ${res.cron_error}`)
      setStep('letters')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function uploadLetters(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    try {
      for (const f of [...files]) {
        if (!f.name.toLowerCase().endsWith('.pdf')) continue
        await apiUpload('/settings/cover-letters', f)
        setLetters((l) => [...l, f.name])
      }
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function doStart() {
    setBusy(true)
    try {
      await startRun([])
      toast.success('Your first search is running. New matches appear on the board over the next 30–60 minutes.')
      navigate('/')
    } catch (e) {
      toast.error(errorMessage(e))
      navigate('/')
    } finally {
      setBusy(false)
    }
  }

  const phone = draft?.profile.personal.phone || ''

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8 md:py-12">
        <div className="flex items-center gap-3">
          <BrandLogo className="size-8" />
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.14em]">jobwright</p>
            <p className="text-xs text-muted-foreground">{me?.email}</p>
          </div>
        </div>
        <Progress step={step} />

        {step === 'name' ? (
          <Panel
            title="Welcome. Let’s set up your job search."
            lead="jobwright finds new roles every morning, scores how well they fit you, and sends the best ones to WhatsApp. Setup takes about five minutes."
          >
            <FormField label="Your name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="First and last name" autoFocus />
            </FormField>
            <Button disabled={!name.trim() || busy} onClick={() => void doCreate()}>
              {busy ? <Loader2 className="animate-spin" /> : <ArrowRight />} Continue
            </Button>
          </Panel>
        ) : null}

        {step === 'resume' ? (
          <Panel
            title="Add your resume"
            lead="We read it to draft your search: the roles to look for, keywords, locations and your dealbreakers. You review everything before it’s saved."
          >
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full items-center gap-3 rounded-xl border border-dashed border-border px-4 py-6 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            >
              {file ? <FileText className="size-6 text-primary" /> : <Upload className="size-6 text-muted-foreground" />}
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {file ? file.name : status?.steps.resume ? 'Resume on file. Upload a new one (optional)' : 'Choose your resume (PDF)'}
                </span>
                <span className="block text-xs text-muted-foreground">PDF only. It stays in your private profile.</span>
              </span>
            </button>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Roles you want (optional)" hint="Helps when your resume doesn't show where you're headed.">
                <Input
                  value={hints.target_roles || ''}
                  onChange={(e) => setHints({ ...hints, target_roles: e.target.value })}
                  placeholder="e.g. program manager at an education nonprofit"
                />
              </FormField>
              <FormField label="Where (optional)">
                <Input
                  value={hints.locations || ''}
                  onChange={(e) => setHints({ ...hints, locations: e.target.value })}
                  placeholder="e.g. Bay Area or remote"
                />
              </FormField>
              <FormField label="Pay floor (optional)">
                <Input
                  value={hints.min_salary || ''}
                  inputMode="numeric"
                  onChange={(e) => setHints({ ...hints, min_salary: e.target.value })}
                  placeholder="e.g. 110000"
                />
              </FormField>
              <FormField label="Never show me (optional)">
                <Input
                  value={hints.avoid || ''}
                  onChange={(e) => setHints({ ...hints, avoid: e.target.value })}
                  placeholder="e.g. sales, fundraising, roles needing a license"
                />
              </FormField>
            </div>
            <Button disabled={busy} onClick={() => void doDraft()}>
              {busy ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {busy ? 'Reading your resume… (up to a minute)' : 'Draft my search'}
            </Button>
          </Panel>
        ) : null}

        {step === 'review' && draft ? (
          <Panel
            title="Here’s what we’ll look for"
            lead="Edit anything that’s off. The better this is, the better your matches."
          >
            <FormField label="Target role" hint="One or two sentences.">
              <Textarea
                rows={3}
                value={draft.profile.experience.target_role || ''}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    profile: { ...draft.profile, experience: { ...draft.profile.experience, target_role: e.target.value } },
                  })
                }
              />
            </FormField>
            <FormField label="Search keywords" hint="Job-board searches run every morning. Daily ones run every day; weekly ones on the deeper weekly crawl.">
              <QueryChipInput
                queries={draft.searches.queries}
                onChange={(queries) => setDraft({ ...draft, searches: { ...draft.searches, queries } })}
              />
            </FormField>
            <FormField label="Where to search" hint="Add a chip named Remote for remote roles.">
              <LocationChipInput
                locations={draft.searches.locations}
                onChange={(locations) => setDraft({ ...draft, searches: { ...draft.searches, locations } })}
              />
            </FormField>
            <FormField label="Phone (with country code)" hint="Used to find WhatsApp chats you're in. Not shared.">
              <Input
                value={phone}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    profile: { ...draft.profile, personal: { ...draft.profile.personal, phone: e.target.value } },
                  })
                }
                placeholder="+1 415 555 0100"
              />
            </FormField>
            <FormField label="Roles to avoid">
              <ChipInput
                values={draft.profile.job_preferences.avoid_roles}
                onChange={(avoid_roles) =>
                  setDraft({
                    ...draft,
                    profile: { ...draft.profile, job_preferences: { ...draft.profile.job_preferences, avoid_roles } },
                  })
                }
                placeholder="Add a role type"
                tone="--destructive"
              />
            </FormField>
            <div className="rounded-xl border border-border/60 p-4">
              <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">How jobs are scored</p>
              <CriteriaEditor compact value={draft.criteria} onChange={(criteria) => setDraft({ ...draft, criteria })} />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep('resume')} disabled={busy}>
                Back
              </Button>
              <Button onClick={() => void doConfirm()} disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <Check />} Save and continue
              </Button>
            </div>
          </Panel>
        ) : null}

        {step === 'whatsapp' ? (
          <Panel
            title="Where should your daily list go?"
            lead="Once a day you get one WhatsApp message with your best new matches. Each links straight to the job here."
          >
            <WhatsAppChatPicker value={target} onChange={setTarget} phone={phone || undefined} />
            <FormField label="Send it at">
              <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="w-40" />
            </FormField>
            <Button onClick={() => void doWhatsApp()} disabled={busy || !target}>
              {busy ? <Loader2 className="animate-spin" /> : <ArrowRight />} Continue
            </Button>
          </Panel>
        ) : null}

        {step === 'letters' ? (
          <Panel
            title="Cover letters you’ve written (optional)"
            lead="Upload a few real letters as PDFs. Tailored letters will sound like you. You can add these later in your profile."
          >
            <input
              ref={lettersRef}
              type="file"
              accept="application/pdf"
              multiple
              className="sr-only"
              onChange={(e) => void uploadLetters(e.target.files)}
            />
            <Button variant="outline" onClick={() => lettersRef.current?.click()} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : <Upload />} Upload PDFs
            </Button>
            {letters.length ? (
              <ul className="space-y-1 text-sm">
                {letters.map((l) => (
                  <li key={l} className="flex items-center gap-2">
                    <Check className="size-4 text-primary" /> {l}
                  </li>
                ))}
              </ul>
            ) : null}
            <Button onClick={() => setStep('done')}>
              <ArrowRight /> {letters.length ? 'Continue' : 'Skip for now'}
            </Button>
          </Panel>
        ) : null}

        {step === 'done' ? (
          <Panel
            title="You’re all set"
            lead="Start your first search now, or wait for tomorrow morning’s run. You can change anything later under Profile."
          >
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void doStart()} disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <Sparkles />} Find my first jobs
              </Button>
              <Button variant="outline" onClick={() => navigate('/')}>
                Go to my board
              </Button>
            </div>
          </Panel>
        ) : null}
      </div>
    </div>
  )
}

import { useEffect, useLayoutEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { StepAbout } from '@/components/welcome/StepAbout'
import { StepDailyList } from '@/components/welcome/StepDailyList'
import { StepFinish } from '@/components/welcome/StepFinish'
import { StepFit } from '@/components/welcome/StepFit'
import { StepLetters } from '@/components/welcome/StepLetters'
import { StepResume } from '@/components/welcome/StepResume'
import { StepSearch } from '@/components/welcome/StepSearch'
import { PROGRESS_LABELS, WelcomeShell } from '@/components/welcome/WelcomeShell'
import { Skeleton } from '@/components/ui/skeleton'
import {
  apiFetch,
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
  type Profile,
  type SettingsData,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { errorMessage } from '@/lib/utils'

type Step = 'name' | 'resume' | 'review' | 'whatsapp' | 'letters' | 'done'
type ReviewPart = 'search' | 'fit'

function firstStepFor(status: OnboardingStatus | null): Step {
  if (!status?.has_profile) return 'name'
  const s = status.steps
  if (!s.resume) return 'resume'
  if (!s.profile || !s.searches) return 'resume'
  if (!s.whatsapp) return 'whatsapp'
  if (!s.cover_letters) return 'letters'
  return 'done'
}

function progressFor(step: Step, part: ReviewPart): number {
  const order: Record<Step, number> = { name: 0, resume: 1, review: 2, whatsapp: 4, letters: 5, done: PROGRESS_LABELS.length }
  return order[step] + (step === 'review' && part === 'fit' ? 1 : 0)
}

function timeFromCron(schedule?: string): string | null {
  const [m, h] = (schedule || '').split(' ')
  if (!/^\d+$/.test(m ?? '') || !/^\d+$/.test(h ?? '')) return null
  return `${h.padStart(2, '0')}:${m.padStart(2, '0')}`
}

export function WelcomePage() {
  const navigate = useNavigate()
  const { me, refresh } = useMe()
  const isAdmin = Boolean(me?.is_admin)
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [step, setStep] = useState<Step>('name')
  const [part, setPart] = useState<ReviewPart>('search')
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [hints, setHints] = useState<DraftHints>({})
  const [draft, setDraft] = useState<OnboardingDraft | null>(null)
  const [target, setTarget] = useState('')
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined)
  const [settings, setSettings] = useState<SettingsData | null | undefined>(undefined)
  const [time, setTime] = useState('07:00')
  const [letters, setLetters] = useState<string[]>([])

  useEffect(() => {
    void getOnboardingStatus()
      .then((s) => {
        setStatus(s)
        setStep(firstStepFor(s))
      })
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => setLoaded(true))
  }, [])

  useLayoutEffect(() => {
    window.scrollTo({ top: 0 })
  }, [step, part])

  useEffect(() => {
    if (step !== 'whatsapp' && step !== 'done') return
    setProfile(undefined)
    void apiFetch<Profile>('/profile')
      .then((p) => {
        setProfile(p)
        if (p.whatsapp_target) setTarget(p.whatsapp_target)
        const t = timeFromCron(p.schedule)
        if (t) setTime(t)
      })
      .catch(() => setProfile(null))
  }, [step])

  useEffect(() => {
    if (step !== 'done') return
    setSettings(undefined)
    void apiFetch<SettingsData>('/settings')
      .then(setSettings)
      .catch(() => setSettings(null))
  }, [step])

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
      const next = await draftSetup(file, hints)
      const typed = phone.trim()
      if (typed) next.profile.personal = { ...next.profile.personal, phone: typed }
      else setPhone(next.profile.personal.phone || '')
      setDraft(next)
      setPart('search')
      setStep('review')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  function toFit() {
    if (!draft?.searches.queries.length) {
      toast.error('Add at least one job title.')
      return
    }
    setPart('fit')
  }

  async function doConfirm() {
    if (!draft) return
    if (!draft.searches.queries.length) {
      toast.error('Add at least one job title.')
      setPart('search')
      return
    }
    setBusy(true)
    try {
      setStatus(await confirmSetup(draft))
      await refresh()
      setStep('whatsapp')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function doWhatsApp() {
    if (isAdmin && !target) {
      toast.error('Pick a chat for their daily list.')
      return
    }
    const [h, m] = time.split(':').map(Number)
    setBusy(true)
    try {
      const res = await updateProfile({
        schedule: `${m} ${h} * * *`,
        ...(isAdmin ? { whatsapp_target: target } : {}),
      })
      if (res.cron_error) toast.info(`Saved. Daily schedule note: ${res.cron_error}`)
      setStep('letters')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function uploadLetters(files: File[]) {
    if (!files.length) return
    setBusy(true)
    try {
      for (const f of files) {
        await apiUpload('/settings/cover-letters', f)
        setLetters((l) => (l.includes(f.name) ? l : [...l, f.name]))
      }
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function toBoard() {
    await refresh()
    navigate('/')
  }

  async function doStart() {
    setBusy(true)
    try {
      await startRun([])
      navigate('/welcome/rate')
    } catch (e) {
      toast.error(errorMessage(e))
      await toBoard()
    } finally {
      setBusy(false)
    }
  }

  function edit(what: 'search' | 'daily' | 'letters') {
    if (what === 'search') {
      if (draft) {
        setPart('search')
        setStep('review')
      } else navigate('/profile?tab=search')
    } else setStep(what === 'daily' ? 'whatsapp' : 'letters')
  }

  const view: Step = step === 'review' && !draft ? 'resume' : step
  let content
  if (!loaded) {
    content = (
      <div className="space-y-4" aria-label="Loading">
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="mt-8 h-11 w-full" />
      </div>
    )
  } else if (view === 'name') {
    content = (
      <StepAbout name={name} onName={setName} phone={phone} onPhone={setPhone} busy={busy} onContinue={() => void doCreate()} />
    )
  } else if (view === 'resume') {
    content = (
      <StepResume
        file={file}
        onFile={setFile}
        hasResume={Boolean(status?.steps.resume)}
        hints={hints}
        onHints={setHints}
        drafting={busy}
        onDraft={() => void doDraft()}
      />
    )
  } else if (view === 'review' && draft) {
    content =
      part === 'search' ? (
        <StepSearch draft={draft} onDraft={setDraft} onBack={() => setStep('resume')} onContinue={toFit} />
      ) : (
        <StepFit
          draft={draft}
          onDraft={setDraft}
          busy={busy}
          onBack={() => setPart('search')}
          onContinue={() => void doConfirm()}
        />
      )
  } else if (view === 'whatsapp') {
    content = (
      <StepDailyList
        isAdmin={isAdmin}
        profile={profile}
        target={target}
        onTarget={setTarget}
        phone={phone || draft?.profile.personal.phone}
        time={time}
        onTime={setTime}
        busy={busy}
        onBack={
          draft
            ? () => {
                setPart('fit')
                setStep('review')
              }
            : undefined
        }
        onContinue={() => void doWhatsApp()}
      />
    )
  } else if (view === 'letters') {
    content = (
      <StepLetters
        letters={letters}
        uploading={busy}
        onUpload={(f) => void uploadLetters(f)}
        onBack={() => setStep('whatsapp')}
        onContinue={() => setStep('done')}
      />
    )
  } else if (view === 'done') {
    content = (
      <StepFinish
        settings={settings}
        profile={profile}
        starting={busy}
        onEdit={edit}
        onBack={() => setStep('letters')}
        onBoard={() => void toBoard()}
        onStart={() => void doStart()}
      />
    )
  }

  return (
    <WelcomeShell progress={progressFor(view, part)} email={me?.email}>
      {content}
    </WelcomeShell>
  )
}

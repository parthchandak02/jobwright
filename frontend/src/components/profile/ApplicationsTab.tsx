import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { SectionHeader } from '@/components/SectionHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getAnswers, getApplyStatus, listPending, type ApplyStatus } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

function statusLine(s: ApplyStatus): { text: string; tone: 'success' | 'warning' | 'secondary' } {
  if (s.kill_switch) return { text: 'Stopped for everyone by the operator', tone: 'warning' }
  if (s.apply_via === 'off') return { text: 'Off. Turn it on in Settings, Claude.', tone: 'secondary' }
  if (s.apply_via === 'connector') {
    if (s.apply_paused) return { text: `Paused: ${s.apply_paused_reason || 'paused'}`, tone: 'warning' }
    return {
      text: `Your own Claude applies (Settings, Claude): up to ${s.apply_daily_cap} a day, ${
        s.apply_enabled ? `submitting on its own for jobs scoring ${s.apply_min_score}+` : 'you press Submit'
      }.`,
      tone: 'success',
    }
  }
  if (!s.apply_enabled) return { text: 'Off. Ask the operator to turn on automatic applications.', tone: 'secondary' }
  if (s.apply_paused) return { text: `Paused: ${s.apply_paused_reason || 'paused'}`, tone: 'warning' }
  const when =
    s.apply_mode === 'veto'
      ? `posted in your WhatsApp group first, sent ${Math.round(s.apply_veto_minutes / 60)} h later unless you reply “skip”`
      : 'sent right after they are picked'
  return {
    text: `On: up to ${s.apply_daily_cap} a day for jobs scoring ${s.apply_min_score}+, ${when}.`,
    tone: 'success',
  }
}

/** Settings → Applications: how applying works for this profile. The answers live in About you. */
export function ApplicationsTab() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<ApplyStatus | null>(null)
  const [missing, setMissing] = useState<number | null>(null)
  const [questions, setQuestions] = useState(0)

  useEffect(() => {
    Promise.all([getAnswers(), getApplyStatus()])
      .then(([a, s]) => {
        setMissing(a.missing.length)
        setStatus(s)
      })
      .catch((e) => toast.error(errorMessage(e)))
    listPending('open')
      .then((r) => setQuestions(r.pending.filter((p) => p.kind === 'answer').length))
      .catch(() => setQuestions(0))
  }, [])

  if (!status) {
    return (
      <div className="space-y-field" aria-busy aria-label="Loading applications">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-11 w-full" />
      </div>
    )
  }

  const line = statusLine(status)
  const parts = [
    questions ? `${questions} question${questions === 1 ? '' : 's'} from your Claude` : '',
    missing ? `${missing} answer${missing === 1 ? '' : 's'} still needed` : '',
  ].filter(Boolean)

  return (
    <div>
      <SectionHeader
        title="Automatic applications"
        description="jobwright applies for you only with your application details and your resume."
      />
      <p className="flex flex-wrap items-center gap-2 text-body text-muted-foreground">
        <Badge variant={line.tone}>{line.tone === 'success' ? 'On' : 'Off'}</Badge>
        {line.text}
      </p>

      <SectionHeader
        title="Application answers"
        description="Your answers for forms (contact and address, education, work eligibility, pay and start date, diversity, other questions) are in About you, Application details."
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" onClick={() => navigate('/profile?tab=about#application-details')}>
          Open application details
        </Button>
        {parts.length ? <Badge variant="warning">{parts.join(' · ')}</Badge> : null}
      </div>
    </div>
  )
}

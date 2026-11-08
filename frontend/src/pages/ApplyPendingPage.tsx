import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, Clock, ShieldQuestion } from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { FormField } from '@/components/FormField'
import { Page } from '@/components/PageHeader'
import { SectionHeader } from '@/components/SectionHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { getPending, pendingScreenshotUrl, providePending, type PendingInput } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

const TITLES: Record<PendingInput['kind'], string> = {
  captcha: 'Finish this one',
  email_code: 'Verification code',
  answer: 'A question for you',
}

function minutesLeft(expires: string | null): number | null {
  if (!expires) return null
  return Math.max(0, Math.round((new Date(expires).getTime() - Date.now()) / 60000))
}

/** /apply/pending/:pendingId: what a paused application is waiting for. */
export function ApplyPendingPage() {
  const { pendingId = '' } = useParams<{ pendingId: string }>()
  const [row, setRow] = useState<PendingInput | null>(null)
  const [missing, setMissing] = useState(false)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(() => Date.now())

  useEffect(() => {
    let alive = true
    const load = () =>
      getPending(pendingId)
        .then((r) => alive && setRow(r))
        .catch(() => alive && setMissing(true))
    void load()
    // The run refreshes its screenshot every few seconds while it waits.
    const t = window.setInterval(() => {
      setTick(Date.now())
      void load()
    }, 4000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [pendingId])

  async function send(v: string) {
    setBusy(true)
    try {
      setRow(await providePending(pendingId, v))
      toast.success('Thanks, the application continues.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (missing) {
    return (
      <Page title="Application request">
        <EmptyState icon={ShieldQuestion} title="Not found" description="This link is for another profile or has been removed." />
      </Page>
    )
  }
  if (!row) {
    return (
      <Page title="Application request">
        <Skeleton className="h-64 w-full" />
      </Page>
    )
  }

  const left = minutesLeft(row.expires_at)
  const open = row.status === 'open'

  return (
    <Page
      title={TITLES[row.kind]}
      description={row.company ? `Application to ${row.company}` : undefined}
      width="wide"
    >
      {!open ? (
        <EmptyState
          icon={row.status === 'resolved' ? CheckCircle2 : Clock}
          title={row.status === 'resolved' ? 'Done' : 'This request has expired'}
          description={
            row.status === 'resolved'
              ? 'The application picked up from here. You get the result in WhatsApp.'
              : 'The application was skipped. It can be tried again on a later day.'
          }
        />
      ) : (
        <>
          <p className="flex flex-wrap items-center gap-2 text-body text-muted-foreground">
            <Badge variant="warning">Waiting</Badge>
            {left != null ? <span className="tabular-nums">About {left} min left.</span> : null}
            {row.prompt}
          </p>

          {row.kind === 'captcha' ? (
            <>
              <SectionHeader
                title="Live view"
                description="The browser runs on the jobwright computer. Solve the check there (screen sharing works), then tap “I solved it”. This picture refreshes every few seconds and cannot be clicked."
              />
              {row.has_screenshot ? (
                <img
                  src={pendingScreenshotUrl(row.id, tick)}
                  alt="Current page of the application"
                  className="w-full rounded-lg border border-border"
                />
              ) : (
                <Skeleton className="h-64 w-full" />
              )}
              <div className="mt-6">
                <Button onClick={() => void send('solved')} disabled={busy}>
                  I solved it
                </Button>
              </div>
            </>
          ) : (
            <form
              className="mt-6 max-w-form space-y-field"
              onSubmit={(e) => {
                e.preventDefault()
                if (value.trim()) void send(value.trim())
              }}
            >
              <FormField
                label={row.kind === 'email_code' ? 'Code from the email' : 'Your answer'}
                htmlFor="pending-value"
                hint={
                  row.kind === 'email_code'
                    ? 'Only used for this application. It is not saved.'
                    : 'Saved for this question, so you are not asked again.'
                }
              >
                <Input
                  id="pending-value"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  autoComplete={row.kind === 'email_code' ? 'one-time-code' : 'off'}
                  inputMode={row.kind === 'email_code' ? 'numeric' : 'text'}
                />
              </FormField>
              <Button type="submit" disabled={busy || !value.trim()}>
                Send
              </Button>
            </form>
          )}
        </>
      )}
    </Page>
  )
}

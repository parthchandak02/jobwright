import { ArrowLeft, ArrowRight, Loader2 } from 'lucide-react'
import { ConnectedChat } from '@/components/ConnectedChat'
import { FormField } from '@/components/FormField'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import type { Profile } from '@/lib/api'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  isAdmin: boolean
  /** `undefined` while loading. */
  profile: Profile | null | undefined
  target: string
  onTarget: (t: string) => void
  phone?: string
  time: string
  onTime: (t: string) => void
  busy: boolean
  onBack?: () => void
  onContinue: () => void
}

export function StepDailyList({
  isAdmin,
  profile,
  target,
  onTarget,
  phone,
  time,
  onTime,
  busy,
  onBack,
  onContinue,
}: Props) {
  const tz = profile?.timezone
  return (
    <WelcomeStep
      title={isAdmin ? 'Their daily list' : 'Your daily list'}
      description={
        isAdmin
          ? 'Pick the WhatsApp chat that gets one message a day with their best new matches.'
          : 'Once a day you’ll get one WhatsApp message with your best new matches. Each one links straight to the job.'
      }
      back={
        onBack ? (
          <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={busy}>
            <ArrowLeft /> Back
          </Button>
        ) : undefined
      }
      actions={
        <Button type="button" size="sm" onClick={onContinue} disabled={busy || (isAdmin && !target)}>
          {busy ? <Loader2 className="animate-spin" /> : null}
          Continue
          {busy ? null : <ArrowRight />}
        </Button>
      }
    >
      <div className="space-y-field">
        {isAdmin ? (
          <FormField label="Send it to" hint={target ? undefined : 'Pick a chat to continue.'}>
            <WhatsAppChatPicker value={target} onChange={onTarget} phone={phone || undefined} />
          </FormField>
        ) : (
          <FormField
            label="Sent to"
            hint={profile?.whatsapp_target ? 'Your admin connected this chat for you.' : undefined}
          >
            {profile === undefined ? (
              <Skeleton className="h-11 w-full" />
            ) : (
              <ConnectedChat target={profile?.whatsapp_target} name={profile?.whatsapp_chat_name} hideTest />
            )}
          </FormField>
        )}
        <FormField label="Send it at" hint="Early morning works well, so it’s waiting when you start your day.">
          <div className="flex items-center gap-3">
            <Input
              type="time"
              value={time}
              onChange={(e) => onTime(e.target.value)}
              className="w-36 tabular-nums"
              aria-label={tz ? `Send time (${tz})` : 'Send time'}
            />
            {tz ? <span className="text-caption text-muted-foreground">{tz}</span> : null}
          </div>
        </FormField>
      </div>
    </WelcomeStep>
  )
}

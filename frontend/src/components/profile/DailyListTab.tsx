import { useState } from 'react'
import { AlertTriangle, MessageCircle, Send, Users } from 'lucide-react'
import type { CSSProperties } from 'react'
import { toast } from 'sonner'
import { ConnectedChat } from '@/components/ConnectedChat'
import { FormField } from '@/components/FormField'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
import { WhatsAppChatPicker, looksUnnamed, type PickedChat } from '@/components/WhatsAppChatPicker'
import { ConfirmAction } from '@/components/profile/ConfirmAction'
import { useAutosave } from '@/components/profile/useAutosave'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { notifyWhatsApp, sendWhatsAppTest, updateProfile, type Profile } from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'

function cronToTime(cron: string | undefined): string {
  const parts = (cron || '0 7 * * *').trim().split(/\s+/)
  if (parts.length !== 5 || !/^\d+$/.test(parts[0]) || !/^\d+$/.test(parts[1])) return '07:00'
  return `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`
}

type Settings = { target: string; time: string; weekly: boolean; followupDays: string }

function clampDays(raw: string): number {
  return Math.min(90, Math.max(1, Math.round(Number(raw)) || 10))
}

function fallbackChatName(target: string): string {
  const digits = target.replace(/\D/g, '')
  return target.endsWith('@g.us') ? `Unnamed group · …${digits.slice(-4)}` : `Chat · …${digits.slice(-4)}`
}

type Props = { profile: Profile; onSaved: () => void }

export function DailyListTab({ profile, onSaved }: Props) {
  const isAdmin = Boolean(useMe().me?.is_admin)
  const [s, setS] = useState<Settings>(() => ({
    target: profile.whatsapp_target || '',
    time: cronToTime(profile.schedule),
    weekly: profile.weekly_summary ?? true,
    followupDays: String(profile.followup_days ?? 10),
  }))
  const [picked, setPicked] = useState<PickedChat | null>(null)
  const [picking, setPicking] = useState(false)
  const [cronError, setCronError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | 'send' | 'test'>(null)

  const autosave = useAutosave(
    async (v: Settings) => {
      const [h, m] = v.time.split(':').map(Number)
      return updateProfile({
        schedule: `${m} ${h} * * *`,
        ...(isAdmin && v.target ? { whatsapp_target: v.target } : {}),
        weekly_summary: v.weekly,
        followup_days: clampDays(v.followupDays),
      })
    },
    {
      onSaved: (res) => {
        setCronError(res.cron_synced === false ? res.cron_error || 'unknown error' : null)
        onSaved()
      },
      onError: (e) => toast.error(errorMessage(e)),
    },
  )

  function patch(p: Partial<Settings>) {
    const next = { ...s, ...p }
    setS(next)
    if (!next.time || !next.followupDays.trim()) return
    autosave.schedule(next)
  }

  const chatType = s.target.endsWith('@g.us') ? 'group' : 'dm'
  const ChatIcon = (picked?.type ?? chatType) === 'group' ? Users : MessageCircle
  const savedName = s.target === profile.whatsapp_target ? profile.whatsapp_chat_name : undefined
  const chatName =
    picked?.name ?? (savedName && !looksUnnamed(savedName) ? savedName.replace(/^whatsapp:/, '') : s.target ? fallbackChatName(s.target) : '')
  const hasChat = Boolean(s.target || profile.whatsapp_target)
  const tz = profile.timezone

  return (
    <div>
      <SectionHeader
        title="Daily list"
        description="Once a day we search, score, and send you one WhatsApp message with your best new matches."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <div className="space-y-field">
        <FormField label="Sent to" hint={!isAdmin && profile.whatsapp_target ? 'Your admin connects this chat for you.' : undefined}>
          {isAdmin ? (
            <div className="space-y-3">
              <div className="flex min-h-14 items-center gap-3 rounded-lg border bg-surface py-2 pr-2 pl-3.5">
                {s.target ? <ChatIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
                <span
                  className={cn('min-w-0 flex-1 truncate text-label', s.target ? 'text-foreground' : 'text-muted-foreground')}
                  title={s.target || undefined}
                >
                  {s.target ? chatName : 'No chat picked yet'}
                </span>
                <Button size="sm" variant="secondary" aria-expanded={picking} onClick={() => setPicking((v) => !v)}>
                  {picking ? 'Done' : s.target ? 'Change' : 'Pick a chat'}
                </Button>
              </div>
              {picking ? (
                <WhatsAppChatPicker
                  hideTest
                  value={s.target}
                  onChange={(target, chat) => {
                    setPicked(chat ?? null)
                    patch({ target })
                  }}
                />
              ) : null}
            </div>
          ) : (
            <ConnectedChat target={profile.whatsapp_target} name={profile.whatsapp_chat_name} />
          )}
        </FormField>

        <FormField
          label="Send time"
          htmlFor="daily-time"
          hint={tz ? `Every day at this time (${tz}).` : 'Every day at this time.'}
        >
          <Input
            id="daily-time"
            type="time"
            value={s.time}
            onChange={(e) => patch({ time: e.target.value })}
            className="w-40 tabular-nums"
          />
        </FormField>

        {cronError ? (
          <div
            className="tone-tint flex gap-2.5 rounded-lg border px-3.5 py-3 text-caption"
            style={{ '--tone': 'var(--warning)' } as CSSProperties}
            role="status"
          >
            <AlertTriangle className="mt-px size-4 shrink-0" aria-hidden />
            <p className="text-foreground">
              Your settings are saved, but the daily schedule couldn’t be updated: {cronError}
            </p>
          </div>
        ) : null}
      </div>

      <SectionHeader title="Summaries and reminders" />
      <ul className="divide-y divide-border rounded-lg border bg-surface">
        <li className="flex items-center gap-4 px-4 py-3.5">
          <label htmlFor="daily-weekly" className="min-w-0 flex-1 cursor-pointer">
            <span className="block text-label text-foreground">Weekly summary</span>
            <span className="mt-0.5 block text-caption text-muted-foreground">
              A short recap every Sunday evening, with the jobs still worth a look.
            </span>
          </label>
          <Switch id="daily-weekly" checked={s.weekly} onCheckedChange={(weekly) => patch({ weekly })} />
        </li>
        <li className="flex items-center gap-4 px-4 py-3.5">
          <label htmlFor="daily-followup" className="min-w-0 flex-1 cursor-pointer">
            <span className="block text-label text-foreground">Follow-up reminders</span>
            <span className="mt-0.5 block text-caption text-muted-foreground">
              We remind you to follow up when a company hasn’t replied after this many days.
            </span>
          </label>
          <div className="relative shrink-0">
            <Input
              id="daily-followup"
              type="number"
              inputMode="numeric"
              min={1}
              max={90}
              value={s.followupDays}
              onChange={(e) => patch({ followupDays: e.target.value })}
              onBlur={() => {
                const days = String(clampDays(s.followupDays))
                if (days !== s.followupDays) patch({ followupDays: days })
              }}
              className="w-24 pr-12 tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-caption text-muted-foreground" aria-hidden>
              days
            </span>
          </div>
        </li>
      </ul>

      <SectionHeader
        title="Send now"
        description="Your list goes out on its own each day. Use this to get today’s list right away."
      />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={!hasChat} onClick={() => setConfirm('send')}>
          <Send />
          Send today’s list now
        </Button>
        {isAdmin ? (
          <Button variant="ghost" disabled={!s.target} onClick={() => setConfirm('test')}>
            Send a test message
          </Button>
        ) : null}
      </div>
      {!hasChat ? (
        <p className="mt-2 text-caption text-muted-foreground">Available once a chat is connected.</p>
      ) : null}

      <ConfirmAction
        open={confirm === 'send'}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Send today’s list now?"
        description="We’ll send your new matches to your WhatsApp chat right away."
        confirmLabel="Send list"
        onConfirm={async () => {
          try {
            const res = await notifyWhatsApp()
            if (res.skipped) toast.info(res.reason || 'Nothing new to send')
            else toast.success(`Sent ${res.sent} ${res.sent === 1 ? 'job' : 'jobs'} to WhatsApp`)
            onSaved()
          } catch (e) {
            toast.error(errorMessage(e))
            throw e
          }
        }}
      />
      <ConfirmAction
        open={confirm === 'test'}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Send a test message?"
        description={`A short test message goes to ${chatName || 'this chat'} now.`}
        confirmLabel="Send test"
        onConfirm={async () => {
          try {
            await sendWhatsAppTest(s.target)
            toast.success('Test message sent. Check WhatsApp.')
          } catch (e) {
            toast.error(errorMessage(e))
            throw e
          }
        }}
      />
    </div>
  )
}

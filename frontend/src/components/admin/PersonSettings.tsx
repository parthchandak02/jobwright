import { useEffect, useState } from 'react'
import { AlertTriangle, Check, ExternalLink, Loader2, Play, Send, Trash2, UserCog } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { ChatField } from '@/components/admin/ChatField'
import { fmtLastBrief, personStatus, toTimeValue } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { AdminOverviewUser, AdminUserPatch } from '@/lib/api'
import { useDebouncedCallback } from '@/lib/useDebouncedCallback'
import { cn } from '@/lib/utils'

export type SaveState = 'saving' | 'saved' | 'error' | undefined

export type PersonActions = {
  onPatch: (patch: AdminUserPatch) => void
  onOpen: (path: '/' | '/profile' | '/welcome') => void
  onSendTest: () => void
  onRun: () => void
  onRemove: () => void
}

type Props = PersonActions & {
  user: AdminOverviewUser
  saveState: SaveState
  id: string
}

const TOP_N = [5, 10, 15, 20, 0]

function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  children: string
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  )
}

function SaveIndicator({ state }: { state: SaveState }) {
  return (
    <span className="flex h-7 items-center gap-1 text-xs text-muted-foreground" aria-live="polite">
      {state === 'saving' ? (
        <>
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Saving…
        </>
      ) : state === 'saved' ? (
        <>
          <Check className="size-3.5 text-(--stage-offer)" aria-hidden /> Saved
        </>
      ) : null}
    </span>
  )
}

export function PersonSettings({ user: u, saveState, id, onPatch, onOpen, onSendTest, onRun, onRemove }: Props) {
  const serverTime = toTimeValue(u.hour, u.minute)
  const [time, setTime] = useState(serverTime)
  const [followup, setFollowup] = useState(String(u.followup_days ?? 10))
  useEffect(() => setTime(serverTime), [serverTime])
  useEffect(() => setFollowup(String(u.followup_days ?? 10)), [u.followup_days])

  const saveTime = useDebouncedCallback((v: string) => {
    const m = v.match(/^(\d{1,2}):(\d{2})$/)
    if (!m || v === serverTime) return
    onPatch({ hour: Number(m[1]), minute: Number(m[2]) })
  })
  const saveFollowup = useDebouncedCallback((v: string) => {
    const n = Math.round(Number(v))
    if (!v || !Number.isFinite(n)) return
    const days = Math.min(90, Math.max(1, n))
    if (days !== u.followup_days) onPatch({ followup_days: days })
  })

  const status = personStatus(u)
  const pending = !u.setup_complete
  const target = u.whatsapp?.target || ''
  const cutoffs = [...new Set([5, 6, 7, 8, 9, ...(u.notify_threshold != null ? [u.notify_threshold] : [])])].sort(
    (a, b) => a - b,
  )
  const rec = u.recommended_threshold
  const problem = status === 'warn' || status === 'fail' ? (u.health?.lines ?? []) : []

  return (
    <div id={id} className="grid gap-x-6 gap-y-4 border-t border-border/60 px-3 py-3 lg:grid-cols-2">
      <div className="min-w-0 space-y-4">
        <FormField label="Login emails" hint="Each email can open only this profile. Cloudflare Access is updated automatically.">
          <ChipInput
            values={u.emails}
            onChange={(emails) => onPatch({ emails })}
            placeholder="name@example.com"
            addLabel={`Add login email for ${u.name}`}
          />
        </FormField>
        <FormField label="WhatsApp chat">
          <ChatField
            value={target}
            name={u.whatsapp?.name}
            type={u.whatsapp?.type}
            onCommit={(whatsapp_target) => {
              if (whatsapp_target !== target) onPatch({ whatsapp_target })
            }}
            actions={
              <Button size="xs" variant="outline" disabled={!target} onClick={onSendTest}>
                <Send /> Send test
              </Button>
            }
          />
          {u.hermes_status === 'add' || u.hermes_status === 'update' ? (
            <p className="text-xs text-muted-foreground">Group instructions need an update (Apply at the top).</p>
          ) : null}
        </FormField>
      </div>

      <div className="min-w-0 space-y-4">
        {u.error ? (
          <p className="flex items-start gap-1 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
            {u.error}
          </p>
        ) : null}
        {pending ? (
          <div className="space-y-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <p>
              Waiting for {u.name} to finish setup at <code>/welcome</code>.
            </p>
            <Button size="xs" variant="outline" onClick={() => onOpen('/welcome')}>
              <UserCog /> Do setup for them
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <FormField label="Daily list at" htmlFor={`${id}-time`}>
                <Input
                  id={`${id}-time`}
                  type="time"
                  value={time}
                  onChange={(e) => {
                    setTime(e.target.value)
                    saveTime(e.target.value)
                  }}
                  className="h-8"
                />
              </FormField>
              <FormField label="Send jobs scoring">
                <Select
                  value={u.notify_threshold != null ? String(u.notify_threshold) : undefined}
                  onValueChange={(v) => onPatch({ notify_threshold: Number(v) })}
                >
                  <SelectTrigger className="h-8" aria-label="Minimum score to send">
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    {cutoffs.map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n}+{rec === n ? ' (recommended)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {rec != null && rec !== u.notify_threshold ? (
                  <p className="text-xs text-muted-foreground">Recommended {rec}+</p>
                ) : null}
              </FormField>
              <FormField label="List size">
                <Select value={String(u.brief_top_n ?? 0)} onValueChange={(v) => onPatch({ brief_top_n: Number(v) })}>
                  <SelectTrigger className="h-8" aria-label="List size">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[...new Set([...TOP_N, u.brief_top_n ?? 0])].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n ? `Top ${n}` : 'All'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <Checkbox checked={u.human_gate} onChange={(human_gate) => onPatch({ human_gate })}>
                Review first
              </Checkbox>
              <Checkbox checked={u.weekly_summary} onChange={(weekly_summary) => onPatch({ weekly_summary })}>
                Weekly summary
              </Checkbox>
              <label className="flex items-center gap-2 text-sm">
                Follow up after
                <Input
                  type="number"
                  min={1}
                  max={90}
                  value={followup}
                  onChange={(e) => {
                    setFollowup(e.target.value)
                    saveFollowup(e.target.value)
                  }}
                  className="h-8 w-16"
                  aria-label="Follow up after days"
                />
                days
              </label>
            </div>
            <div className="space-y-0.5 text-xs">
              <p className="text-muted-foreground">Last list: {fmtLastBrief(u)}</p>
              {problem.map((line, i) => (
                <p
                  key={i}
                  className={cn('flex items-start gap-1', status === 'fail' ? 'text-destructive' : 'text-(--stage-in-progress)')}
                >
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                  {line}
                </p>
              ))}
              {u.brief_cron === false ? (
                <p className="text-(--stage-in-progress)">No daily schedule yet. Change the time or chat to create it.</p>
              ) : null}
            </div>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 lg:col-span-2">
        <Button size="xs" variant="outline" onClick={() => onOpen('/')}>
          <ExternalLink /> Open board
        </Button>
        <Button size="xs" variant="outline" onClick={() => onOpen('/profile')}>
          <UserCog /> Open profile
        </Button>
        <Button size="xs" variant="outline" disabled={pending || !target} onClick={onRun}>
          <Play /> Run search now
        </Button>
        <SaveIndicator state={saveState} />
        <Button size="xs" variant="ghost" className="ml-auto text-destructive hover:text-destructive" onClick={onRemove}>
          <Trash2 /> Remove
        </Button>
      </div>
    </div>
  )
}

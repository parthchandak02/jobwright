import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, LayoutGrid, MoreHorizontal, Play, Trash2, UserCog } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { ChatField } from '@/components/admin/ChatField'
import { StatusDot } from '@/components/admin/StatusDot'
import { fmtLastBrief, personStatus, toTimeValue } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
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

type Props = Pick<PersonActions, 'onPatch' | 'onOpen'> & {
  user: AdminOverviewUser
  id: string
  /** `inline` = two columns in the desktop row; `sheet` = one column in the phone sheet. */
  layout?: 'inline' | 'sheet'
}

const TOP_N = [5, 10, 15, 20, 0]

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-4 text-subheading text-foreground">{title}</h3>
      <div className="space-y-field">{children}</div>
    </section>
  )
}

function SwitchRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <Label htmlFor={id}>{label}</Label>
        <p id={`${id}-hint`} className="mt-0.5 text-caption text-muted-foreground">
          {hint}
        </p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} aria-describedby={`${id}-hint`} className="mt-0.5" />
    </div>
  )
}

/** One line: last list and any problem, shown above the settings. */
export function PersonHealth({ user: u }: { user: AdminOverviewUser }) {
  const status = personStatus(u)
  const problem = status === 'warn' || status === 'fail' ? (u.health?.lines ?? []) : []
  const pending = !u.setup_complete
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-2 text-caption text-muted-foreground">
        <StatusDot status={status} />
        {pending ? (
          <span>Invited. Their daily list starts once they finish setup.</span>
        ) : (
          <span>
            <span className="text-foreground">Last list:</span> {fmtLastBrief(u)}
          </span>
        )}
      </p>
      {u.error || problem.length || (!pending && u.brief_cron === false) ? (
        <div
          className={cn(
            'space-y-1 rounded-md bg-surface-muted px-3 py-2.5 text-caption',
            status === 'fail' ? 'text-destructive' : 'text-foreground',
          )}
        >
          {u.error ? <ProblemLine>{u.error}</ProblemLine> : null}
          {problem.map((line, i) => (
            <ProblemLine key={i}>{line}</ProblemLine>
          ))}
          {!pending && u.brief_cron === false ? (
            <ProblemLine>No daily schedule yet. Change the time or chat to create it.</ProblemLine>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function ProblemLine({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </p>
  )
}

export function PersonSettings({ user: u, id, onPatch, onOpen, layout = 'inline' }: Props) {
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

  const pending = !u.setup_complete
  const target = u.whatsapp?.target || ''
  const cutoffs = [...new Set([5, 6, 7, 8, 9, ...(u.notify_threshold != null ? [u.notify_threshold] : [])])].sort(
    (a, b) => a - b,
  )
  const rec = u.recommended_threshold
  const first = u.name.split(' ')[0] || u.name

  return (
    <div className={cn('grid gap-x-10 gap-y-8', layout === 'inline' && 'lg:grid-cols-2')}>
      <Group title="Login">
        <FormField label="Login emails" hint="Each email opens only this profile. Login access updates automatically.">
          <ChipInput
            values={u.emails}
            onChange={(emails) => onPatch({ emails })}
            placeholder="Add a login email"
            addLabel={`Add login email for ${u.name}`}
          />
        </FormField>
        <FormField
          label="WhatsApp chat"
          htmlFor={`${id}-chat`}
          hint={
            u.hermes_status === 'add' || u.hermes_status === 'update'
              ? 'Group instructions need an update. Apply them under System.'
              : 'Where their daily list is posted.'
          }
        >
          <ChatField
            id={`${id}-chat`}
            value={target}
            name={u.whatsapp?.name}
            type={u.whatsapp?.type}
            onCommit={(whatsapp_target) => {
              if (whatsapp_target !== target) onPatch({ whatsapp_target })
            }}
          />
        </FormField>
      </Group>

      <Group title="Daily list">
        {pending ? (
          <div className="space-y-3 rounded-md bg-surface-muted px-4 py-3.5">
            <p className="text-body text-muted-foreground">
              Waiting for {first} to add a resume and profile at their first login. You can also do it for them.
            </p>
            <Button size="sm" variant="secondary" onClick={() => onOpen('/welcome')}>
              <UserCog /> Do setup for them
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-x-4 gap-y-field sm:grid-cols-3">
              <FormField label="Sends at" htmlFor={`${id}-time`}>
                <Input
                  id={`${id}-time`}
                  type="time"
                  value={time}
                  onChange={(e) => {
                    setTime(e.target.value)
                    saveTime(e.target.value)
                  }}
                />
              </FormField>
              <FormField
                label="Cutoff"
                htmlFor={`${id}-cutoff`}
                hint={rec != null && rec !== u.notify_threshold ? `Recommended ${rec}+` : 'Minimum score'}
              >
                <Select
                  value={u.notify_threshold != null ? String(u.notify_threshold) : undefined}
                  onValueChange={(v) => onPatch({ notify_threshold: Number(v) })}
                >
                  <SelectTrigger id={`${id}-cutoff`} className="w-full">
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
              </FormField>
              <FormField label="List size" htmlFor={`${id}-size`} className="col-span-2 sm:col-span-1">
                <Select value={String(u.brief_top_n ?? 0)} onValueChange={(v) => onPatch({ brief_top_n: Number(v) })}>
                  <SelectTrigger id={`${id}-size`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[...new Set([...TOP_N, u.brief_top_n ?? 0])].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n ? `Top ${n}` : 'All matches'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>
            </div>
            <SwitchRow
              id={`${id}-gate`}
              label="Review first"
              hint="Send a short list to review. Resumes are made only for jobs they pick."
              checked={u.human_gate}
              onChange={(human_gate) => onPatch({ human_gate })}
            />
            <SwitchRow
              id={`${id}-weekly`}
              label="Weekly summary"
              hint="A short recap on WhatsApp every Sunday evening."
              checked={u.weekly_summary}
              onChange={(weekly_summary) => onPatch({ weekly_summary })}
            />
            <FormField
              label="Follow-up reminder"
              htmlFor={`${id}-followup`}
              hint="Days after applying with no news before we remind them."
            >
              <div className="flex items-center gap-2">
                <Input
                  id={`${id}-followup`}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={90}
                  value={followup}
                  onChange={(e) => {
                    setFollowup(e.target.value)
                    saveFollowup(e.target.value)
                  }}
                  className="w-20 tabular-nums"
                />
                <span className="text-body text-muted-foreground">days</span>
              </div>
            </FormField>
          </>
        )}
      </Group>
    </div>
  )
}

type ActionsProps = Omit<PersonActions, 'onPatch'> & { user: AdminOverviewUser; className?: string }

/** Navigation (ghost), real-world sends (secondary with icon, confirmed), Remove in the "⋯" menu. */
export function PersonActionBar({ user: u, onOpen, onSendTest, onRun, onRemove, className }: ActionsProps) {
  const pending = !u.setup_complete
  const target = u.whatsapp?.target || ''
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <div className="flex items-center gap-1 max-sm:w-full max-sm:[&>*]:flex-1">
        <Button size="sm" variant="ghost" onClick={() => onOpen('/')}>
          <LayoutGrid /> Open board
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onOpen('/profile')}>
          <UserCog /> Open profile
        </Button>
      </div>
      <div className="flex flex-1 items-center justify-end gap-2 max-sm:w-full">
        <Button
          size="sm"
          variant="secondary"
          disabled={!target}
          title={target ? undefined : 'Pick a chat first'}
          onClick={onSendTest}
          className="max-sm:flex-1"
        >
          <WhatsAppIcon className="text-muted-foreground" /> Send test
        </Button>
        {!pending ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={!target}
            title={target ? undefined : 'Pick a chat first'}
            onClick={onRun}
            className="max-sm:flex-1"
          >
            <Play /> Run search now
          </Button>
        ) : null}
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label={`More actions for ${u.name}`} className="max-sm:size-11">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem variant="destructive" onSelect={onRemove}>
              <Trash2 /> Remove {u.name.split(' ')[0] || 'person'}…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

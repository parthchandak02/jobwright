import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, Shield, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { RunProgressDialog } from '@/components/RunProgressDialog'
import { AddPersonDialog } from '@/components/admin/AddPersonDialog'
import { AdminsAlertsSection } from '@/components/admin/AdminsAlertsSection'
import { AiUsageSection } from '@/components/admin/AiUsageSection'
import { ConfirmDialog } from '@/components/admin/ConfirmDialog'
import { PersonRow, PersonRowSkeleton } from '@/components/admin/PersonRow'
import type { SaveState } from '@/components/admin/PersonSettings'
import { SystemStrip } from '@/components/admin/SystemStrip'
import { chatName, reportAccessSync, scheduleLabel } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import {
  deleteAdminUser,
  getAdminOverview,
  patchAdminUser,
  sendAdminTestMessage,
  startAdminRun,
  switchProfile,
  type AdminOverview,
  type AdminOverviewUser,
  type AdminUserPatch,
  type RunHandle,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { RUN_STAGE_LABELS } from '@/lib/useAutoSearch'
import { useRunStream } from '@/lib/useRunStream'
import { cn, errorMessage } from '@/lib/utils'

type UserFields = keyof AdminOverviewUser

const PATCH_FIELDS: Record<keyof AdminUserPatch, UserFields[]> = {
  name: ['name'],
  emails: ['emails'],
  whatsapp_target: ['whatsapp'],
  hour: ['hour', 'schedule', 'schedule_label'],
  minute: ['minute', 'schedule', 'schedule_label'],
  schedule: ['schedule', 'schedule_label', 'hour', 'minute'],
  notify_threshold: ['notify_threshold'],
  brief_top_n: ['brief_top_n'],
  human_gate: ['human_gate'],
  weekly_summary: ['weekly_summary'],
  followup_days: ['followup_days'],
}

function applyPatch(u: AdminOverviewUser, p: AdminUserPatch): AdminOverviewUser {
  const next: AdminOverviewUser = { ...u }
  if (p.name !== undefined) next.name = p.name
  if (p.emails !== undefined) next.emails = p.emails
  if (p.whatsapp_target !== undefined) next.whatsapp = { target: p.whatsapp_target || null, name: null, type: null }
  if (p.hour !== undefined) {
    next.hour = p.hour
    next.minute = p.minute ?? 0
    next.schedule = `${next.minute} ${next.hour} * * *`
    next.schedule_label = scheduleLabel(next.hour, next.minute)
  }
  if (p.notify_threshold !== undefined) next.notify_threshold = p.notify_threshold
  if (p.brief_top_n !== undefined) next.brief_top_n = p.brief_top_n
  if (p.human_gate !== undefined) next.human_gate = p.human_gate
  if (p.weekly_summary !== undefined) next.weekly_summary = p.weekly_summary
  if (p.followup_days !== undefined) next.followup_days = p.followup_days
  return next
}

function revertPatch(u: AdminOverviewUser, before: AdminOverviewUser, p: AdminUserPatch): AdminOverviewUser {
  const next = { ...u } as Record<UserFields, unknown>
  for (const key of Object.keys(p) as (keyof AdminUserPatch)[]) {
    for (const f of PATCH_FIELDS[key] ?? []) next[f] = before[f]
  }
  return next as AdminOverviewUser
}

type Pending = { kind: 'test' | 'run' | 'remove'; user: AdminOverviewUser; open: boolean } | null

function chatLabel(u: AdminOverviewUser) {
  return chatName(u.whatsapp?.name) || 'their WhatsApp chat'
}

/** Admin: people, their daily list settings, logins, alerts and system health. */
export function AdminPage() {
  const { me, refresh: refreshMe } = useMe()
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<Record<string, SaveState>>({})
  const [adding, setAdding] = useState(false)
  const [pending, setPending] = useState<Pending>(null)
  const [deleteData, setDeleteData] = useState(false)
  const [run, setRun] = useState<{ handle: RunHandle; name: string } | null>(null)

  const overviewRef = useRef(overview)
  useEffect(() => {
    overviewRef.current = overview
  }, [overview])
  const seq = useRef<Record<string, number>>({})
  const savedTimers = useRef<Record<string, number>>({})

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    void getAdminOverview()
      .then(setOverview)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  const refreshSystem = useCallback(() => {
    void getAdminOverview()
      .then((res) =>
        setOverview((prev) => {
          if (!prev) return res
          const byId = new Map(res.users.map((u) => [u.user_id, u]))
          return {
            ...res,
            users: prev.users.map((u) => {
              const fresh = byId.get(u.user_id)
              return fresh ? { ...u, hermes_status: fresh.hermes_status, whatsapp: fresh.whatsapp } : u
            }),
          }
        }),
      )
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (me?.is_admin) load()
  }, [me?.is_admin, load])

  const stream = useRunStream(run?.handle ?? null, load)

  const updateUser = useCallback((userId: string, fn: (u: AdminOverviewUser) => AdminOverviewUser) => {
    setOverview((prev) =>
      prev ? { ...prev, users: prev.users.map((u) => (u.user_id === userId ? fn(u) : u)) } : prev,
    )
  }, [])

  const markSave = useCallback((userId: string, state: SaveState) => {
    window.clearTimeout(savedTimers.current[userId])
    setSaveState((s) => ({ ...s, [userId]: state }))
    if (state === 'saved') {
      savedTimers.current[userId] = window.setTimeout(
        () => setSaveState((s) => ({ ...s, [userId]: undefined })),
        2000,
      )
    }
  }, [])

  const patchUser = useCallback(
    async (userId: string, patch: AdminUserPatch) => {
      const before = overviewRef.current?.users.find((u) => u.user_id === userId)
      if (!before) return
      const n = (seq.current[userId] ?? 0) + 1
      seq.current[userId] = n
      updateUser(userId, (u) => applyPatch(u, patch))
      markSave(userId, 'saving')
      try {
        const res = await patchAdminUser(userId, patch)
        if (seq.current[userId] === n) {
          if (res.user) updateUser(userId, () => res.user!)
          markSave(userId, 'saved')
        }
        reportAccessSync(res.access_sync)
        if (res.cron && (res.cron.ok === false || res.cron.error)) {
          toast.error(`Saved, but the daily schedule was not updated: ${res.cron.error || 'unknown error'}`)
        }
        if (patch.emails || patch.whatsapp_target !== undefined || patch.name) refreshSystem()
      } catch (e) {
        updateUser(userId, (u) => revertPatch(u, before, patch))
        if (seq.current[userId] === n) markSave(userId, 'error')
        toast.error(`Could not save ${before.name}: ${errorMessage(e)}`)
      }
    },
    [markSave, refreshSystem, updateUser],
  )

  const openAs = useCallback((userId: string, path: string) => {
    void switchProfile(userId)
      .then(() => window.location.assign(path))
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  async function confirmPending() {
    if (!pending) return
    const u = pending.user
    try {
      if (pending.kind === 'test') {
        await sendAdminTestMessage(u.user_id)
        toast.success(`Test message sent to ${chatLabel(u)}`)
      } else if (pending.kind === 'run') {
        const handle = await startAdminRun(u.user_id)
        try {
          await switchProfile(u.user_id)
          void refreshMe()
          toast.info(`Switched to ${u.name} to follow the run`)
        } catch (e) {
          toast.error(`Run started, but live progress is unavailable: ${errorMessage(e)}`)
          return
        }
        setRun({ handle, name: u.name })
      } else {
        await deleteAdminUser(u.user_id, deleteData)
        toast.success(`Removed ${u.name}`)
        setDeleteData(false)
        if (expanded === u.user_id) setExpanded(null)
        load()
        void refreshMe()
      }
    } catch (e) {
      toast.error(errorMessage(e))
      throw e
    }
  }

  function closePending(open: boolean) {
    if (!open) setPending((p) => (p ? { ...p, open: false } : p))
  }

  const pendingName = pending?.user.name ?? ''
  const pendingChat = pending ? chatLabel(pending.user) : ''

  if (me && !me.is_admin) {
    return <p className="p-6 text-sm text-muted-foreground">Admins only.</p>
  }

  const users = overview?.users ?? null
  const setupPending = users?.filter((u) => !u.setup_complete).length ?? 0

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className={cn(APP_SHELL_HEADER, 'sticky top-0 z-20')}>
        <Shield className="size-4 text-muted-foreground" />
        <h1 className="text-xs font-bold uppercase tracking-wider">Admin</h1>
        <Button
          size="icon-sm"
          variant="ghost"
          className="ml-auto"
          onClick={load}
          disabled={loading}
          aria-label="Refresh"
        >
          <RefreshCw className={cn(loading && 'animate-spin')} />
        </Button>
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        <div className="mx-auto w-full max-w-5xl space-y-6">
          {error && !overview ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 text-destructive">Could not load the admin overview: {error}</span>
              <Button size="xs" variant="outline" onClick={load}>
                Retry
              </Button>
            </div>
          ) : (
            <SystemStrip overview={overview} onChanged={refreshSystem} />
          )}

          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold">People</h2>
              {users ? (
                <span className="text-xs text-muted-foreground">
                  {users.length}
                  {setupPending ? ` · ${setupPending} setting up` : ''}
                </span>
              ) : null}
              <Button size="sm" variant="outline" className="ml-auto" onClick={() => setAdding(true)}>
                <UserPlus /> Add person
              </Button>
            </div>
            <ul className="glass divide-y divide-border/60 overflow-hidden rounded-xl" aria-busy={!users && !error}>
              {!users ? (
                error ? (
                  <li className="px-3 py-6 text-center text-xs text-muted-foreground">People could not be loaded.</li>
                ) : (
                  [0, 1, 2].map((i) => <PersonRowSkeleton key={i} />)
                )
              ) : !users.length ? (
                <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No one yet. Add a person to start their daily list.
                </li>
              ) : (
                users.map((u) => (
                  <PersonRow
                    key={u.user_id}
                    user={u}
                    expanded={expanded === u.user_id}
                    onToggle={() => setExpanded((cur) => (cur === u.user_id ? null : u.user_id))}
                    saveState={saveState[u.user_id]}
                    onPatch={(patch) => void patchUser(u.user_id, patch)}
                    onOpen={(path) => openAs(u.user_id, path)}
                    onSendTest={() => setPending({ kind: 'test', user: u, open: true })}
                    onRun={() => setPending({ kind: 'run', user: u, open: true })}
                    onRemove={() => {
                      setDeleteData(false)
                      setPending({ kind: 'remove', user: u, open: true })
                    }}
                  />
                ))
              )}
            </ul>
          </section>

          <AdminsAlertsSection
            settings={overview?.settings ?? null}
            onSaved={(settings, refresh) => {
              setOverview((prev) => (prev ? { ...prev, settings } : prev))
              if (refresh) refreshSystem()
            }}
          />
          <AiUsageSection />
        </div>
      </main>

      <AddPersonDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={() => {
          load()
          void refreshMe()
        }}
      />

      <ConfirmDialog
        open={pending?.kind === 'test' && pending.open}
        onOpenChange={closePending}
        title={`Send a test message to ${pendingName}?`}
        description={`This posts a hello in ${pendingChat}. It is a real chat, so ${pendingName} will see it.`}
        confirmLabel="Send test"
        onConfirm={confirmPending}
      />
      <ConfirmDialog
        open={pending?.kind === 'run' && pending.open}
        onOpenChange={closePending}
        title={`Run ${pendingName}’s search now?`}
        description={`Searches and scores new jobs, then sends the list to ${pendingChat}. ${pendingName} will get a WhatsApp message.`}
        confirmLabel="Run and send"
        onConfirm={confirmPending}
      />
      <ConfirmDialog
        open={pending?.kind === 'remove' && pending.open}
        onOpenChange={closePending}
        title={`Remove ${pendingName}?`}
        description="Their daily search stops and they lose access. Keep the data unless you are sure."
        confirmLabel="Remove"
        destructive
        onConfirm={confirmPending}
      >
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={deleteData} onChange={(e) => setDeleteData(e.target.checked)} />
          Also delete their jobs, resume and files (cannot be undone)
        </label>
      </ConfirmDialog>

      <RunProgressDialog
        open={!!run}
        onClose={() => {
          setRun(null)
          load()
        }}
        title={run ? `Daily list for ${run.name}` : 'Daily list'}
        description="Search, score, then send their WhatsApp list. Closing this window does not stop the run."
        stageLabels={{ ...RUN_STAGE_LABELS, notify: 'Sending list' }}
        run={stream}
      />
    </div>
  )
}

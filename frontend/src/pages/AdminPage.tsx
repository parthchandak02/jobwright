import { useCallback, useEffect, useState } from 'react'
import { Bell, Loader2, Plus, RefreshCw, Shield, Trash2, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { ChipInput } from '@/components/ChipInput'
import { Chip } from '@/components/Chip'
import { FormField } from '@/components/FormField'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  createProfile,
  deleteAdminUser,
  ensureWatchdog,
  getAdminCosts,
  getAdminSettings,
  getAdminUsers,
  patchAdminUser,
  putAdminSettings,
  sendOpsTest,
  switchProfile,
  type AdminCosts,
  type AdminSettings,
  type AdminUser,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'

function HealthChip({ user }: { user: AdminUser }) {
  const level = user.health?.level
  const today = user.brief_today.join(' · ')
  if (!level && !today) return <Chip muted>No brief yet today</Chip>
  const tone = level === 'fail' ? '--destructive' : level === 'warn' ? '--stage-in-progress' : '--stage-offer'
  return (
    <Chip tone={tone} title={[...(user.health?.lines || []), today].join('\n')}>
      {level === 'fail' ? 'Problem' : level === 'warn' ? 'Warning' : 'Healthy'}
    </Chip>
  )
}

function fmtCost(v: number | null): string {
  return v == null ? 'no price set' : `$${v.toFixed(2)}`
}

function CostsSection({ costs }: { costs: AdminCosts | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">AI usage, last {costs?.days ?? 30} days</h2>
      <p className="text-xs text-muted-foreground">
        Tokens per profile from each profile’s own usage log. Cost is an estimate from JOBWRIGHT_LLM_PRICES.
      </p>
      {!costs ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </p>
      ) : (
        <div className="glass overflow-x-auto rounded-xl p-4">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="pb-2 font-medium">Profile</th>
                <th className="pb-2 text-right font-medium">Calls</th>
                <th className="pb-2 text-right font-medium">Tokens</th>
                <th className="pb-2 text-right font-medium">Est. cost</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {costs.users.map((u) => (
                <tr key={u.user_id} className="border-t border-border/60">
                  <td className="py-1.5">
                    {u.name}
                    {u.error ? <span className="ml-2 text-xs text-muted-foreground">({u.error})</span> : null}
                  </td>
                  <td className="py-1.5 text-right">{u.calls.toLocaleString()}</td>
                  <td className="py-1.5 text-right">{u.total_tokens.toLocaleString()}</td>
                  <td className="py-1.5 text-right">{fmtCost(u.cost_usd)}</td>
                </tr>
              ))}
              <tr className="border-t border-border font-semibold">
                <td className="pt-2">Total</td>
                <td className="pt-2 text-right">{costs.total.calls.toLocaleString()}</td>
                <td className="pt-2 text-right">{costs.total.total_tokens.toLocaleString()}</td>
                <td className="pt-2 text-right">{fmtCost(costs.total.cost_usd)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/** Admin: who can log in to which profile, alert routing, health. */
export function AdminPage() {
  const { me, refresh: refreshMe } = useMe()
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [settings, setSettings] = useState<AdminSettings | null>(null)
  const [costs, setCosts] = useState<AdminCosts | null>(null)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [toDelete, setToDelete] = useState<AdminUser | null>(null)
  const [deleteData, setDeleteData] = useState(false)

  const load = useCallback(() => {
    void Promise.all([getAdminUsers(), getAdminSettings()])
      .then(([u, s]) => {
        setUsers(u.users)
        setSettings(s)
      })
      .catch((e) => toast.error(errorMessage(e)))
    void getAdminCosts()
      .then(setCosts)
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  useEffect(() => {
    if (me?.is_admin) load()
  }, [me?.is_admin, load])

  async function saveEmails(u: AdminUser, emails: string[]) {
    try {
      await patchAdminUser(u.user_id, { emails })
      setUsers((prev) => prev?.map((x) => (x.user_id === u.user_id ? { ...x, emails } : x)) ?? prev)
      toast.success(`Logins updated for ${u.name}`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  async function create() {
    if (!newName.trim() || !newEmail.trim()) return
    setBusy(true)
    try {
      await createProfile(newName.trim(), [newEmail.trim().toLowerCase()])
      toast.success('Profile created. They finish setup the first time they log in.')
      setNewName('')
      setNewEmail('')
      load()
      void refreshMe()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function saveSettings(patch: Partial<AdminSettings>) {
    try {
      setSettings(await putAdminSettings(patch))
      toast.success('Saved')
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  async function confirmDelete() {
    if (!toDelete) return
    setBusy(true)
    try {
      await deleteAdminUser(toDelete.user_id, deleteData)
      toast.success(`Removed ${toDelete.name}`)
      setToDelete(null)
      load()
      void refreshMe()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (me && !me.is_admin) {
    return <p className="p-6 text-sm text-muted-foreground">Admins only.</p>
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className={cn(APP_SHELL_HEADER, 'sticky top-0 z-20')}>
        <Shield className="size-4 text-muted-foreground" />
        <h1 className="text-xs font-bold uppercase tracking-wider">Admin</h1>
        <Button size="icon-sm" variant="ghost" className="ml-auto" onClick={load} aria-label="Refresh">
          <RefreshCw />
        </Button>
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        <div className="mx-auto w-full max-w-5xl space-y-8">
          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Profiles</h2>
            <p className="text-xs text-muted-foreground">
              Each login email sees only its own profile. New people also need their email allowed in Cloudflare
              Access (Zero Trust → Access → Applications → jobwright → policy).
            </p>
            {!users ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading…
              </p>
            ) : (
              <div className="space-y-3">
                {users.map((u) => (
                  <div key={u.user_id} className="glass space-y-3 rounded-xl p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{u.name}</p>
                      <span className="text-xs text-muted-foreground">{u.user_id}</span>
                      <HealthChip user={u} />
                      <div className="ml-auto flex gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void switchProfile(u.user_id)
                              .then(() => window.location.assign('/'))
                              .catch((e) => toast.error(errorMessage(e)))
                          }
                        >
                          Open
                        </Button>
                        <Button size="icon-sm" variant="ghost" aria-label={`Remove ${u.name}`} onClick={() => setToDelete(u)}>
                          <Trash2 />
                        </Button>
                      </div>
                    </div>
                    <FormField label="Login emails">
                      <ChipInput
                        values={u.emails}
                        onChange={(emails) => void saveEmails(u, emails)}
                        placeholder="name@example.com"
                        addLabel="Add email"
                      />
                    </FormField>
                    <p className="text-xs text-muted-foreground">
                      WhatsApp: {u.whatsapp_target ? 'set' : 'not set'} · {u.schedule_label || u.schedule} ·{' '}
                      {u.human_gate ? 'review first' : 'materials automatically'} · top {u.brief_top_n || 'all'}
                    </p>
                  </div>
                ))}
              </div>
            )}
            <div className="glass grid gap-2 rounded-xl p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <FormField label="New person’s name">
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} className="h-8" />
              </FormField>
              <FormField label="Their login email">
                <Input value={newEmail} type="email" onChange={(e) => setNewEmail(e.target.value)} className="h-8" />
              </FormField>
              <Button size="sm" onClick={() => void create()} disabled={busy || !newName.trim() || !newEmail.trim()}>
                <UserPlus /> Create profile
              </Button>
            </div>
          </section>

          <CostsSection costs={costs} />

          <section className="space-y-4">
            <h2 className="text-sm font-semibold">Admins and alerts</h2>
            {settings ? (
              <>
                <FormField label="Admin emails" hint="Admins can open and manage every profile.">
                  <ChipInput
                    values={settings.admins}
                    onChange={(admins) => void saveSettings({ admins })}
                    placeholder="admin@example.com"
                    addLabel="Add admin"
                  />
                </FormField>
                <FormField
                  label="Send operator alerts to"
                  hint="Where problems go: failed searches, empty lists, WhatsApp delivery failures, missed runs."
                >
                  <WhatsAppChatPicker
                    value={settings.ops_target}
                    onChange={(ops_target) => void saveSettings({ ops_target })}
                  />
                </FormField>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void ensureWatchdog()
                        .then((r) => (r.ok ? toast.success('Daily health check scheduled (8:30 AM)') : toast.error(r.error || 'Failed')))
                        .catch((e) => toast.error(errorMessage(e)))
                    }
                  >
                    <Plus /> Schedule daily health check
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void sendOpsTest()
                        .then((r) => toast.info(r.result))
                        .catch((e) => toast.error(errorMessage(e)))
                    }
                  >
                    <Bell /> Send test alert
                  </Button>
                </div>
              </>
            ) : null}
          </section>
        </div>
      </main>

      <Dialog open={!!toDelete} onOpenChange={(v) => !v && setToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Remove {toDelete?.name}?</DialogTitle>
            <DialogDescription>
              Their daily search stops and they lose access. Keep the data unless you are sure.
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={deleteData} onChange={(e) => setDeleteData(e.target.checked)} />
            Also delete their jobs, resume and files (cannot be undone)
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()} disabled={busy}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

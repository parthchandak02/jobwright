import { useEffect, useRef, useState } from 'react'
import { Info, Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { ActionBar } from '@/components/ActionBar'
import { CriteriaEditor } from '@/components/CriteriaEditor'
import { SectionHeader } from '@/components/SectionHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getCriteria, saveCriteria, suggestCriteria, type MatchCriteria } from '@/lib/api'
import { invalidateReasons } from '@/lib/reasons'
import { errorMessage } from '@/lib/utils'

export function RulesTab() {
  const [criteria, setCriteria] = useState<MatchCriteria | null>(null)
  const [derived, setDerived] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<null | 'save' | 'suggest'>(null)
  const saved = useRef<MatchCriteria | null>(null)

  useEffect(() => {
    void getCriteria()
      .then((r) => {
        saved.current = r.criteria
        setCriteria(r.criteria)
        setDerived(r.derived)
      })
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  async function save() {
    if (!criteria) return
    setBusy('save')
    try {
      const r = await saveCriteria(criteria)
      saved.current = r.criteria
      setCriteria(r.criteria)
      setDerived(false)
      setDirty(false)
      invalidateReasons()
      toast.success('Rules saved. New jobs will be scored with them.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  async function suggest() {
    setBusy('suggest')
    try {
      const r = await suggestCriteria()
      setCriteria(r.criteria)
      setDirty(true)
      toast.success(
        r.based_on_ratings
          ? `Drafted from your resume and ${r.based_on_ratings} ratings. Review, then save.`
          : 'Drafted from your resume. Review, then save.',
      )
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  function discard() {
    if (saved.current) setCriteria(saved.current)
    setDirty(false)
  }

  const suggestButton = (
    <Button size="sm" variant="ai" onClick={() => void suggest()} disabled={!!busy || !criteria}>
      {busy === 'suggest' ? <Loader2 className="animate-spin" /> : <Sparkles />}
      {busy === 'suggest' ? 'Suggesting…' : 'Suggest from my ratings'}
    </Button>
  )

  return (
    <div>
      <SectionHeader
        title="How we judge fit"
        description="Every new job is compared with these rules and the jobs you’ve rated."
        actions={<span className="hidden md:inline-flex">{suggestButton}</span>}
      />
      <div className="-mt-1 mb-6 md:hidden">{suggestButton}</div>
      {derived && !dirty ? (
        <div className="mb-6 flex gap-3 rounded-lg bg-surface-muted px-4 py-3 text-caption text-muted-foreground">
          <Info className="mt-px size-4 shrink-0 text-primary" aria-hidden />
          <p>
            We filled these in from your profile. Adjust anything that’s off and save, or let us suggest rules from the
            jobs you’ve rated.
          </p>
        </div>
      ) : null}
      {criteria ? (
        <CriteriaEditor
          value={criteria}
          onChange={(next) => {
            setCriteria(next)
            setDirty(true)
          }}
        />
      ) : (
        <div className="space-y-field" aria-busy>
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-20 w-full" />
            </div>
          ))}
        </div>
      )}
      <ActionBar
        open={dirty || derived}
        message={dirty ? 'You have unsaved changes' : 'These rules aren’t saved yet'}
        onDiscard={dirty ? discard : undefined}
        onSave={() => void save()}
        saveLabel="Save rules"
        saving={busy === 'save'}
        saveDisabled={busy === 'suggest'}
      />
    </div>
  )
}

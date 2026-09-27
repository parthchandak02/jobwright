import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { CollapsibleSection } from '@/components/admin/CollapsibleSection'
import { fmtTokens } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { getAdminCosts, type AdminCosts } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

function fmtUsd(v: number | null): string {
  return v == null ? '—' : `$${v.toFixed(2)}`
}

export function AiUsageSection() {
  const [costs, setCosts] = useState<AdminCosts | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function load() {
    setLoading(true)
    setError('')
    void getAdminCosts()
      .then(setCosts)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }

  return (
    <CollapsibleSection
      title="AI usage"
      summary="Last 30 days, per profile"
      onOpenChange={(open) => {
        if (open && !costs) load()
      }}
    >
      {error ? (
        <div className="flex items-center gap-2 text-xs text-destructive">
          {error}
          <Button size="xs" variant="outline" onClick={load}>
            Retry
          </Button>
        </div>
      ) : !costs || loading ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Loading…
        </p>
      ) : (
        <div className="space-y-2">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <table className="w-full text-xs tabular-nums">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Profile</th>
                  <th className="px-3 py-1.5 text-right font-medium">Calls</th>
                  <th className="px-3 py-1.5 text-right font-medium">Tokens</th>
                  <th className="px-3 py-1.5 text-right font-medium">Est. cost</th>
                </tr>
              </thead>
              <tbody>
                {costs.users.map((u) => (
                  <tr key={u.user_id} className="border-t border-border/60">
                    <td className="px-3 py-1.5 text-sm">
                      {u.name}
                      {u.error ? <span className="ml-2 text-xs text-muted-foreground">({u.error})</span> : null}
                    </td>
                    <td className="px-3 py-1.5 text-right">{u.calls.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right" title={u.total_tokens.toLocaleString()}>
                      {fmtTokens(u.total_tokens)}
                    </td>
                    <td className="px-3 py-1.5 text-right">{fmtUsd(u.cost_usd)}</td>
                  </tr>
                ))}
                <tr className="border-t border-border font-semibold">
                  <td className="px-3 py-1.5 text-sm">Total</td>
                  <td className="px-3 py-1.5 text-right">{costs.total.calls.toLocaleString()}</td>
                  <td className="px-3 py-1.5 text-right" title={costs.total.total_tokens.toLocaleString()}>
                    {fmtTokens(costs.total.total_tokens)}
                  </td>
                  <td className="px-3 py-1.5 text-right">{fmtUsd(costs.total.cost_usd)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">Cost is an estimate from JOBWRIGHT_LLM_PRICES.</p>
        </div>
      )}
    </CollapsibleSection>
  )
}

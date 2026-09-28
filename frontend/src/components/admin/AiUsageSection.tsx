import { useState } from 'react'
import { CollapsibleSection } from '@/components/admin/CollapsibleSection'
import { fmtTokens, fmtUsd } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getAdminCosts, type AdminCosts } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

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

  const cell = 'px-4 py-2.5 text-right md:px-5'

  return (
    <CollapsibleSection
      title="AI usage"
      summary="Last 30 days, per person"
      onOpenChange={(open) => {
        if (open && !costs) load()
      }}
    >
      {error ? (
        <div className="flex flex-wrap items-center gap-3 text-caption text-destructive">
          <span className="min-w-0 flex-1">Couldn't load AI usage: {error}</span>
          <Button size="sm" variant="secondary" onClick={load}>
            Retry
          </Button>
        </div>
      ) : !costs || loading ? (
        <div className="space-y-2" aria-busy>
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <div className="space-y-2">
          <div className="surface overflow-x-auto rounded-lg">
            <table className="w-full text-body tabular-nums">
              <thead className="text-caption text-muted-foreground">
                <tr className="border-b">
                  <th className="px-4 py-2.5 text-left font-normal md:px-5">Person</th>
                  <th className={`${cell} font-normal`}>AI calls</th>
                  <th className={`${cell} font-normal`}>Tokens</th>
                  <th className={`${cell} font-normal`}>Est. cost</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {costs.users.map((u) => (
                  <tr key={u.user_id}>
                    <td className="px-4 py-2.5 md:px-5">
                      {u.name}
                      {u.error ? <span className="ml-2 text-caption text-muted-foreground">({u.error})</span> : null}
                    </td>
                    <td className={cell}>{u.calls.toLocaleString()}</td>
                    <td className={cell} title={`${u.total_tokens.toLocaleString()} tokens`}>
                      {fmtTokens(u.total_tokens)}
                    </td>
                    <td className={cell}>{fmtUsd(u.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t font-medium">
                  <td className="px-4 py-2.5 md:px-5">Total</td>
                  <td className={cell}>{costs.total.calls.toLocaleString()}</td>
                  <td className={cell} title={`${costs.total.total_tokens.toLocaleString()} tokens`}>
                    {fmtTokens(costs.total.total_tokens)}
                  </td>
                  <td className={cell}>{fmtUsd(costs.total.cost_usd)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="text-caption text-muted-foreground">
            Costs are estimates. A dash means no price is set for that model.
          </p>
        </div>
      )}
    </CollapsibleSection>
  )
}

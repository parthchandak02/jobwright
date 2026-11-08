import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useServerVersion } from '@/components/UpdateNotifier'
import { CLIENT_BUILD, isUpdateAvailable, updatesEnabled, versionLine } from '@/lib/version'
import { cn } from '@/lib/utils'

/** "Version abc1234 · updated Nov 8, 3:12 PM" for the build this tab runs (dev server: the server's). */
export function useVersionLine(): string {
  const server = useServerVersion()
  if (updatesEnabled(CLIENT_BUILD.build_id)) return versionLine(CLIENT_BUILD.sha, CLIENT_BUILD.built_at)
  return versionLine(server?.version, server?.built_at ?? server?.deployed_at)
}

/**
 * Quiet footer for Settings: the running version, a Refresh when a newer one is deployed, and
 * "What's new" (recent changes, from the server's git log) behind a disclosure.
 */
export function AppVersion({ className }: { className?: string }) {
  const server = useServerVersion()
  const line = useVersionLine()
  const ready = isUpdateAvailable(CLIENT_BUILD.build_id, server)
  const changes = server?.changes ?? []

  return (
    <footer className={cn('border-t border-border pt-6 text-caption text-muted-foreground', className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="tabular-nums">{line}</p>
        {ready ? (
          <Button size="xs" variant="secondary" onClick={() => window.location.reload()}>
            New version ready · Refresh
          </Button>
        ) : null}
      </div>
      {changes.length ? (
        <details className="group mt-2">
          <summary className="relative inline-flex cursor-pointer list-none items-center gap-1 rounded-md touch-target hover:text-foreground [&::-webkit-details-marker]:hidden">
            <ChevronRight className="size-3.5 transition-transform duration-(--dur-1) group-open:rotate-90" aria-hidden />
            What’s new
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {changes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </footer>
  )
}

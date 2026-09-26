import { Loader2, LogIn, RefreshCw } from 'lucide-react'
import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { BrandLogo } from '@/components/BrandLogo'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { useMe } from '@/lib/me'

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background p-6 text-center">
      <BrandLogo className="size-10 text-muted-foreground" />
      {children}
    </div>
  )
}

/** Blocks the app until we know who is logged in; sends new logins to onboarding. */
export function AppGate({ children }: { children: ReactNode }) {
  const { me, loading, error, refresh } = useMe()
  const location = useLocation()

  if (loading) {
    return (
      <Centered>
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </Centered>
    )
  }

  if (error || !me) {
    const expired = error instanceof ApiError && error.status === 401
    return (
      <Centered>
        <div className="max-w-sm space-y-2">
          <h1 className="text-base font-semibold">{expired ? 'Please sign in again' : 'Could not reach jobwright'}</h1>
          <p className="text-sm text-muted-foreground">
            {expired
              ? 'Your login session ended. Reload to get a new sign-in code by email.'
              : error?.message || 'The server did not respond.'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => window.location.reload()}>
            {expired ? <LogIn /> : <RefreshCw />} Reload
          </Button>
          {!expired ? (
            <Button size="sm" variant="outline" onClick={() => void refresh()}>
              Try again
            </Button>
          ) : null}
        </div>
      </Centered>
    )
  }

  const onWelcome = location.pathname.startsWith('/welcome')
  if (!me.active_user && !onWelcome) return <Navigate to="/welcome" replace />
  return <>{children}</>
}

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RefreshCw, TriangleAlert } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'

type Props = {
  children: ReactNode
  /** Clears the error when it changes (e.g. the route path), so moving on recovers. */
  resetKey?: unknown
}

type State = { error: Error | null }

/** Catches render errors (and failed lazy page loads) so one broken page never blanks the app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed', error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="flex min-w-0 flex-1 items-start justify-center px-page-x">
        <EmptyState
          size="page"
          icon={TriangleAlert}
          title="Something went wrong"
          description="This page hit a problem. Reloading usually fixes it, and nothing you saved is lost."
          action={
            <>
              <Button variant="secondary" onClick={() => window.location.reload()}>
                <RefreshCw /> Reload
              </Button>
              <Button variant="ghost" onClick={() => window.location.assign('/')}>
                Back to the board
              </Button>
            </>
          }
        />
      </div>
    )
  }
}

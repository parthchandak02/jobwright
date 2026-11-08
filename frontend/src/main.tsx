import { StrictMode, Suspense, lazy, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AppGate } from '@/components/AppGate'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { PageSkeleton } from '@/components/PageSkeleton'
import { Toaster } from '@/components/ui/sonner'
import { MeProvider } from '@/lib/me'
import { ThemeProvider } from '@/lib/theme'
import App from './App'
import './index.css'

const WelcomePage = lazy(() => import('@/pages/WelcomePage').then((m) => ({ default: m.WelcomePage })))
const CalibrationPage = lazy(() => import('@/pages/CalibrationPage').then((m) => ({ default: m.CalibrationPage })))

function Lazy({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full">
          <PageSkeleton />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

/** One error boundary around every route; navigating to another path clears a crash. */
function AppRoutes() {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary resetKey={pathname}>
      <Routes>
        <Route
          path="/welcome"
          element={
            <Lazy>
              <WelcomePage />
            </Lazy>
          }
        />
        <Route
          path="/welcome/rate"
          element={
            <Lazy>
              <CalibrationPage />
            </Lazy>
          }
        />
        <Route path="/" element={<App />} />
        <Route path="/profile" element={<App />} />
        <Route path="/quality" element={<App />} />
        <Route path="/admin" element={<App />} />
        <Route path="/review" element={<App />} />
        <Route path="/jobs/:jobId" element={<App />} />
        <Route path="/apply/pending/:pendingId" element={<App />} />
        <Route path="/apply/submissions/:submissionId" element={<App />} />
        <Route path="*" element={<App />} />
      </Routes>
    </ErrorBoundary>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <MeProvider>
          <AppGate>
            <AppRoutes />
          </AppGate>
        </MeProvider>
        <Toaster
          richColors
          position="bottom-right"
          // Phones: sit above the bottom tab bar / drawer action bar (56px + safe area).
          phoneBottom="calc(4.5rem + env(safe-area-inset-bottom, 0px))"
        />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)

import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppGate } from '@/components/AppGate'
import { Toaster } from '@/components/ui/sonner'
import { MeProvider } from '@/lib/me'
import { ThemeProvider } from '@/lib/theme'
import App from './App'
import './index.css'

const WelcomePage = lazy(() => import('@/pages/WelcomePage').then((m) => ({ default: m.WelcomePage })))
const CalibrationPage = lazy(() => import('@/pages/CalibrationPage').then((m) => ({ default: m.CalibrationPage })))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <MeProvider>
          <AppGate>
            <Routes>
              <Route
                path="/welcome"
                element={
                  <Suspense fallback={null}>
                    <WelcomePage />
                  </Suspense>
                }
              />
              <Route
                path="/welcome/rate"
                element={
                  <Suspense fallback={null}>
                    <CalibrationPage />
                  </Suspense>
                }
              />
              <Route path="/" element={<App />} />
              <Route path="/profile" element={<App />} />
              <Route path="/quality" element={<App />} />
              <Route path="/admin" element={<App />} />
              <Route path="/jobs/:jobId" element={<App />} />
              <Route path="*" element={<App />} />
            </Routes>
          </AppGate>
        </MeProvider>
        <Toaster richColors position="bottom-right" />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)

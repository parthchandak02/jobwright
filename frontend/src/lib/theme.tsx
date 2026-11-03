import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

/** What the person picked. `system` follows the device (prefers-color-scheme). */
export type ThemePreference = 'light' | 'dark' | 'system'
/** What is on screen right now. */
export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'jobwright-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

type ThemeContextValue = {
  /** Resolved theme on screen (light or dark). */
  theme: Theme
  preference: ThemePreference
  setPreference: (preference: ThemePreference) => void
  /** Light → Dark → System → Light. */
  cycleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

/** New visitors (nothing stored) follow the device; an earlier light/dark pick is kept. */
function readStoredPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    /* ignore */
  }
  return 'system'
}

function systemTheme(): Theme {
  return typeof window !== 'undefined' && window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light'
}

function applyDomTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

const NEXT: Record<ThemePreference, ThemePreference> = { light: 'dark', dark: 'system', system: 'light' }

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    typeof window === 'undefined' ? 'system' : readStoredPreference(),
  )
  const [system, setSystem] = useState<Theme>(systemTheme)

  useEffect(() => {
    const mq = window.matchMedia?.(DARK_QUERY)
    if (!mq) return
    const onChange = () => setSystem(mq.matches ? 'dark' : 'light')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const theme: Theme = preference === 'system' ? system : preference

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }, [])

  const cycleTheme = useCallback(() => setPreference(NEXT[preference]), [preference, setPreference])

  useEffect(() => {
    applyDomTheme(theme)
  }, [theme])

  const value = useMemo(
    () => ({ theme, preference, setPreference, cycleTheme }),
    [theme, preference, setPreference, cycleTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, getMe, type Me } from '@/lib/api'

type MeState = {
  me: Me | null
  loading: boolean
  error: ApiError | Error | null
  refresh: () => Promise<Me | null>
}

const MeContext = createContext<MeState | null>(null)

export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | Error | null>(null)

  const refresh = useCallback(async () => {
    try {
      const next = await getMe()
      setMe(next)
      setError(null)
      return next
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => ({ me, loading, error, refresh }), [me, loading, error, refresh])
  return <MeContext.Provider value={value}>{children}</MeContext.Provider>
}

export function useMe(): MeState {
  const ctx = useContext(MeContext)
  if (!ctx) throw new Error('useMe outside MeProvider')
  return ctx
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, Loader2, Plus, Search, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiFetch } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

export type ConnectionContact = {
  id?: string
  name?: string
  first_name?: string
  last_name?: string
  company?: string
  position?: string
  role?: string
  email?: string
  url?: string
  source_url?: string
  why?: string
  note?: string
  rank_score?: number
  source?: string
}

export type ConnectionsData = {
  csv_contacts: ConnectionContact[]
  web_contacts: ConnectionContact[]
  manual_contacts: ConnectionContact[]
}

type SearchResult = ConnectionContact

type Props = {
  jobKey: string
  connections: ConnectionsData | null
  onChanged: () => void
}

function displayName(c: ConnectionContact): string {
  const explicit = (c.name || '').trim()
  if (explicit) return explicit
  const parts = [c.first_name, c.last_name].filter(Boolean).join(' ').trim()
  return parts || 'Contact'
}

function subtitle(c: ConnectionContact): string | null {
  const role = (c.position || c.role || '').trim()
  const company = (c.company || '').trim()
  if (role && company) return `${role} · ${company}`
  return role || company || null
}

function ContactRow({
  contact,
  onRemove,
  removing,
}: {
  contact: ConnectionContact
  onRemove?: () => void
  removing?: boolean
}) {
  const name = displayName(contact)
  const meta = subtitle(contact)
  const href = (contact.url || contact.source_url || '').trim()
  const why = (contact.why || contact.note || '').trim()
  const isManual = contact.source === 'manual'

  return (
    <li className="connection-row">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-label break-words text-foreground underline-offset-2 hover:underline"
            >
              {name}
            </a>
          ) : (
            <span className="text-label break-words text-foreground">{name}</span>
          )}
          {isManual ? <Badge variant="secondary">Added by you</Badge> : null}
        </div>
        {meta ? <p className="text-caption break-words text-muted-foreground">{meta}</p> : null}
        {why ? <p className="mt-0.5 line-clamp-2 text-caption break-words text-muted-foreground">{why}</p> : null}
      </div>

      <div className="-mr-1 flex shrink-0 items-center">
        {href ? (
          <Button asChild type="button" size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground">
            <a href={href} target="_blank" rel="noreferrer" aria-label={`Open ${name} on LinkedIn`}>
              <ExternalLink className="size-3.5" />
            </a>
          </Button>
        ) : null}
        {onRemove ? (
          <Button
            type="button"
            size="icon-sm"
            variant="destructive-ghost"
            disabled={removing}
            onClick={onRemove}
            aria-label={`Remove ${name}`}
          >
            <Trash2 className="size-3.5" />
          </Button>
        ) : null}
      </div>
    </li>
  )
}

export function ConnectionsPanel({ jobKey, connections, onChanged }: Props) {
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchBusy, setSearchBusy] = useState(false)
  const [profileUrl, setProfileUrl] = useState('')
  const [profileName, setProfileName] = useState('')
  const [busy, setBusy] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const searchBoxRef = useRef<HTMLDivElement>(null)

  const suggested = useMemo(() => {
    const csv = connections?.csv_contacts || []
    const web = connections?.web_contacts || []
    return [...csv, ...web]
  }, [connections])

  const manual = connections?.manual_contacts || []
  const hasAny = suggested.length > 0 || manual.length > 0

  useEffect(() => {
    const q = search.trim()
    if (q.length < 2) {
      setSearchResults([])
      setSearchOpen(false)
      return
    }
    const timer = setTimeout(() => {
      setSearchBusy(true)
      void apiFetch<{ results: SearchResult[] }>(
        `/connections/search?q=${encodeURIComponent(q)}&limit=8`,
      )
        .then((res) => {
          setSearchResults(res.results || [])
          setSearchOpen(true)
        })
        .catch(() => setSearchResults([]))
        .finally(() => setSearchBusy(false))
    }, 250)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!searchBoxRef.current?.contains(e.target as Node)) {
        setSearchOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  async function addFromSearch(contact: SearchResult) {
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobKey)}/connections`, {
        method: 'POST',
        body: JSON.stringify({
          first_name: contact.first_name,
          last_name: contact.last_name,
          company: contact.company,
          position: contact.position,
          email: contact.email,
          url: contact.url,
        }),
      })
      setSearch('')
      setSearchResults([])
      setSearchOpen(false)
      onChanged()
      toast.success('Connection added')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function addFromUrl() {
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobKey)}/connections`, {
        method: 'POST',
        body: JSON.stringify({
          url: profileUrl.trim(),
          name: profileName.trim() || undefined,
        }),
      })
      setProfileUrl('')
      setProfileName('')
      onChanged()
      toast.success('Connection added')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function removeContact(contactId: string) {
    setRemovingId(contactId)
    try {
      await apiFetch(
        `/jobs/${encodeURIComponent(jobKey)}/connections/${encodeURIComponent(contactId)}`,
        { method: 'DELETE' },
      )
      onChanged()
      toast.success('Connection removed')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <div className="min-w-0 space-y-4">
      {!hasAny ? (
        <p className="text-caption text-muted-foreground">
          No LinkedIn contacts found at this employer yet. Search your connections or paste a profile link.
        </p>
      ) : (
        <ul className="min-w-0">
          {suggested.map((c, i) => (
            <ContactRow key={`s-${i}-${displayName(c)}`} contact={c} />
          ))}
          {manual.map((c) => (
            <ContactRow
              key={c.id || displayName(c)}
              contact={c}
              removing={removingId === c.id}
              onRemove={c.id ? () => void removeContact(c.id!) : undefined}
            />
          ))}
        </ul>
      )}

      <div className="space-y-2">
        <div ref={searchBoxRef} className="relative">
          <label htmlFor="conn-search" className="sr-only">
            Search your connections
          </label>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            id="conn-search"
            value={search}
            placeholder="Search your connections"
            disabled={busy}
            className="pl-9"
            autoComplete="off"
            onChange={(e) => setSearch(e.target.value)}
            onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
          />
          {searchOpen && (searchResults.length > 0 || searchBusy) ? (
            <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-popover border bg-popover p-1 shadow-e1">
              {searchBusy ? (
                <li className="flex items-center gap-2 px-2.5 py-2 text-caption text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" /> Searching…
                </li>
              ) : (
                searchResults.map((c, i) => (
                  <li key={`${c.url || ''}-${i}`}>
                    <button
                      type="button"
                      className="flex min-h-11 w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors duration-(--dur-1) hover:bg-surface-muted md:min-h-0"
                      disabled={busy}
                      onClick={() => void addFromSearch(c)}
                    >
                      <Plus className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0">
                        <span className="block text-label text-foreground">{displayName(c)}</span>
                        {subtitle(c) ? <span className="block text-caption text-muted-foreground">{subtitle(c)}</span> : null}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </div>

        <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
          <label htmlFor="conn-url" className="sr-only">
            LinkedIn profile link
          </label>
          <Input
            id="conn-url"
            value={profileUrl}
            placeholder="Paste a LinkedIn profile link"
            disabled={busy}
            className="min-w-0 sm:flex-[2]"
            onChange={(e) => setProfileUrl(e.target.value)}
          />
          <div className="flex min-w-0 gap-2 sm:flex-1">
            <Input
              value={profileName}
              placeholder="Name (optional)"
              disabled={busy}
              className="min-w-0 flex-1"
              aria-label="Contact name (optional)"
              onChange={(e) => setProfileName(e.target.value)}
            />
            <Button
              type="button"
              variant="secondary"
              className="shrink-0"
              disabled={busy || !profileUrl.trim()}
              onClick={() => void addFromUrl()}
            >
              Add
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

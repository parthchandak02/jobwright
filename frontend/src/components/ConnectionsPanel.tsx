import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, Loader2, Plus, Trash2, UserRound } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiFetch } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

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
  why?: string
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
  jobUrl: string
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
  const href = contact.url?.trim()
  const isManual = contact.source === 'manual'

  return (
    <li className="connection-row">
      <div className="connection-avatar" aria-hidden>
        <UserRound />
      </div>

      <div className="connection-body">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="connection-name linkedin-link"
            >
              {name}
            </a>
          ) : (
            <span className="connection-name">{name}</span>
          )}
          {isManual ? <span className="connection-added">Added</span> : null}
        </div>
        {meta ? <p className="connection-meta">{meta}</p> : null}
        {contact.why ? <p className="connection-why">{contact.why}</p> : null}
      </div>

      <div className="flex shrink-0 items-center -mr-1">
        {href ? (
          <Button
            asChild
            type="button"
            size="icon-sm"
            variant="ghost"
            className="linkedin-link hover:bg-[var(--linkedin-muted)]"
          >
            <a href={href} target="_blank" rel="noreferrer" aria-label={`Open ${name} on LinkedIn`}>
              <ExternalLink className="size-3" />
            </a>
          </Button>
        ) : null}
        {onRemove ? (
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="text-muted-foreground hover:text-destructive"
            disabled={removing}
            onClick={onRemove}
            aria-label={`Remove ${name}`}
          >
            <Trash2 className="size-3" />
          </Button>
        ) : null}
      </div>
    </li>
  )
}

export function ConnectionsPanel({ jobUrl, connections, onChanged }: Props) {
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
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}/connections`, {
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
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}/connections`, {
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
        `/jobs/${encodeURIComponent(jobUrl)}/connections/${encodeURIComponent(contactId)}`,
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
    <div className="connections-panel min-w-0">
      {!hasAny ? (
        <p className="text-xs text-muted-foreground">No contacts yet.</p>
      ) : (
        <ul className="connections-list min-w-0">
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

      <div className="connections-add">
        <div ref={searchBoxRef} className="relative">
          <label htmlFor="conn-search" className="sr-only">
            Search connections
          </label>
          <Input
            id="conn-search"
            value={search}
            placeholder="Search connections…"
            disabled={busy}
            className="connections-add-input"
            onChange={(e) => setSearch(e.target.value)}
            onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
          />
          {searchOpen && (searchResults.length > 0 || searchBusy) ? (
            <ul
              className={cn(
                'absolute z-20 mt-1 max-h-44 w-full overflow-auto rounded-md border border-border/80 bg-popover p-0.5 shadow-md',
              )}
            >
              {searchBusy ? (
                <li className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" /> Searching…
                </li>
              ) : (
                searchResults.map((c, i) => (
                  <li key={`${c.url || ''}-${i}`}>
                    <button
                      type="button"
                      className="connections-search-item"
                      disabled={busy}
                      onClick={() => void addFromSearch(c)}
                    >
                      <Plus className="mt-0.5 size-3 shrink-0 linkedin-link" />
                      <span className="min-w-0">
                        <span className="connections-search-item-name">{displayName(c)}</span>
                        {subtitle(c) ? (
                          <span className="block text-[0.6875rem] text-muted-foreground">
                            {subtitle(c)}
                          </span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </div>

        <div className="connections-url-row">
          <label htmlFor="conn-url" className="sr-only">
            LinkedIn profile URL
          </label>
          <Input
            id="conn-url"
            value={profileUrl}
            placeholder="Paste LinkedIn URL"
            disabled={busy}
            className="connections-add-input"
            onChange={(e) => setProfileUrl(e.target.value)}
          />
          <Input
            value={profileName}
            placeholder="Name (optional)"
            disabled={busy}
            className="connections-add-input"
            aria-label="Contact name (optional)"
            onChange={(e) => setProfileName(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
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
  )
}

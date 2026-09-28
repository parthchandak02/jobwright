import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { AlertTriangle, Check, Loader2, MessageCircle, RefreshCw, Send, Users } from 'lucide-react'
import { toast } from 'sonner'
import { Chip } from '@/components/Chip'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { listWhatsAppChats, sendWhatsAppTest, type WhatsAppChat, type WhatsAppChats } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

export type PickedChat = { name: string; type: 'group' | 'dm' }

type Props = {
  value: string
  onChange: (target: string, chat?: PickedChat) => void
  /** Phone (with country code) used to find chats that include the user. */
  phone?: string
  className?: string
  /** Hide the built-in test-send button (when the caller provides its own). */
  hideTest?: boolean
}

export function looksUnnamed(name: string | null | undefined, id?: string): boolean {
  const n = (name || '').replace(/^whatsapp:/, '').trim()
  if (!n) return true
  if (id && n === id) return true
  return /^[\d@.\-\s+]+(g\.us|s\.whatsapp\.net)?$/i.test(n) && /\d{8,}/.test(n)
}

export function chatDisplayName(chat: Pick<WhatsAppChat, 'name' | 'id' | 'target' | 'type'>): string {
  if (!looksUnnamed(chat.name, chat.id)) return chat.name.replace(/^whatsapp:/, '')
  const digits = (chat.id || chat.target).replace(/\D/g, '')
  const tail = digits.slice(-4)
  return chat.type === 'group' ? `Unnamed group · …${tail}` : `Chat · …${tail}`
}

/** Admin-only: pick where a profile's daily job list is posted (every chat the bot is in). */
export function WhatsAppChatPicker({ value, onChange, phone, className, hideTest }: Props) {
  const [data, setData] = useState<WhatsAppChats | null>(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('')
  const [testing, setTesting] = useState(false)
  const [manual, setManual] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await listWhatsAppChats(phone))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [phone])

  useEffect(() => {
    void load()
  }, [load])

  const chats = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return (data?.chats || []).filter((c) => !q || chatDisplayName(c).toLowerCase().includes(q))
  }, [data, filter])

  async function test() {
    if (!value) return
    setTesting(true)
    try {
      await sendWhatsAppTest(value)
      toast.success('Test message sent. Check WhatsApp.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setTesting(false)
    }
  }

  const bridgeDown = data && data.bridge !== 'connected'

  return (
    <div className={cn('space-y-3', className)}>
      {bridgeDown ? (
        <div
          className="tone-tint flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-caption"
          style={{ '--tone': 'var(--warning)' } as CSSProperties}
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span className="text-foreground">
            The WhatsApp connection is offline right now, so chat names may be missing and test messages
            will fail. You can still pick a chat; the daily list resumes when it reconnects.
          </span>
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search chats"
          aria-label="Search WhatsApp chats"
        />
        <Button type="button" size="icon" variant="secondary" onClick={() => void load()} aria-label="Refresh chats">
          {loading ? <Loader2 className="animate-spin" /> : <RefreshCw />}
        </Button>
      </div>

      <div role="radiogroup" aria-label="WhatsApp chat" className="max-h-80 space-y-0.5 overflow-y-auto overscroll-contain rounded-lg border bg-surface p-1">
        {data?.direct_target ? (
          <ChatRow
            selected={value === data.direct_target}
            onSelect={() => onChange(data.direct_target!, { name: 'Message me directly', type: 'dm' })}
            icon={MessageCircle}
            name="Message me directly"
            detail="Sent to your own WhatsApp number"
          />
        ) : null}
        {chats.map((c) => (
          <ChatRow
            key={c.target}
            selected={value === c.target}
            onSelect={() => onChange(c.target, { name: chatDisplayName(c), type: c.type })}
            icon={c.type === 'group' ? Users : MessageCircle}
            name={chatDisplayName(c)}
            unnamed={looksUnnamed(c.name, c.id)}
            detail={c.type === 'group' ? `Group${c.participants ? ` · ${c.participants} people` : ''}` : 'Direct chat'}
            badge={c.includes_you ? 'You’re in it' : undefined}
          />
        ))}
        {!loading && !chats.length && !data?.direct_target ? (
          <p className="px-4 py-8 text-center text-caption text-muted-foreground">
            {data?.filtered
              ? 'No chats with your number yet. Add your phone number to your profile, or create a WhatsApp group with the jobwright number and refresh.'
              : 'No chats found.'}
          </p>
        ) : null}
        {loading && !data ? (
          <p className="flex items-center justify-center gap-2 px-4 py-8 text-caption text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Loading chats…
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {hideTest ? null : (
          <Button type="button" size="sm" variant="secondary" disabled={!value || testing} onClick={() => void test()}>
            {testing ? <Loader2 className="animate-spin" /> : <Send />} Send a test message
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" className="text-muted-foreground" aria-expanded={manual} onClick={() => setManual((v) => !v)}>
          {manual ? 'Hide chat id' : 'Enter a chat id instead'}
        </Button>
      </div>
      {manual ? (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value.trim())}
          placeholder="Paste a chat id"
          className="font-mono"
          aria-label="WhatsApp chat id"
        />
      ) : null}
    </div>
  )
}

function ChatRow({
  selected,
  onSelect,
  icon: Icon,
  name,
  detail,
  badge,
  unnamed,
}: {
  selected: boolean
  onSelect: () => void
  icon: typeof Users
  name: string
  detail: string
  badge?: string
  unnamed?: boolean
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'flex min-h-14 w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors duration-(--dur-1) focus-visible:outline-offset-[-2px] md:min-h-12',
        selected ? 'bg-accent' : 'hover:bg-surface-muted',
      )}
    >
      <Icon className={cn('size-4 shrink-0', selected ? 'text-accent-foreground' : 'text-muted-foreground')} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className={cn('block truncate text-label', unnamed ? 'text-muted-foreground' : 'text-foreground', selected && 'text-accent-foreground')}>{name}</span>
        <span className="block truncate text-caption text-muted-foreground">{detail}</span>
      </span>
      {badge ? <Chip className="shrink-0 max-sm:hidden">{badge}</Chip> : null}
      {selected ? <Check className="size-4 shrink-0 text-primary" aria-hidden /> : null}
    </button>
  )
}

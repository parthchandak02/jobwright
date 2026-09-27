import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Check, Loader2, MessageCircle, RefreshCw, Send, Users } from 'lucide-react'
import { toast } from 'sonner'
import { Chip } from '@/components/Chip'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { listWhatsAppChats, sendWhatsAppTest, type WhatsAppChats } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  value: string
  onChange: (target: string) => void
  /** Phone (with country code) used to find chats that include the user. */
  phone?: string
  className?: string
  /** Hide the built-in test-send button (when the caller provides its own). */
  hideTest?: boolean
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
    return (data?.chats || []).filter((c) => !q || c.name.toLowerCase().includes(q))
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
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
          <span>
            The WhatsApp connection is offline right now, so chat names may be missing and test messages
            will fail. You can still pick a chat; the daily list resumes when it reconnects.
          </span>
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search chats…"
          className="h-8"
          aria-label="Search WhatsApp chats"
        />
        <Button type="button" size="icon-sm" variant="outline" onClick={() => void load()} aria-label="Refresh chats">
          {loading ? <Loader2 className="animate-spin" /> : <RefreshCw />}
        </Button>
      </div>

      <div role="radiogroup" aria-label="WhatsApp chat" className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-border/60 p-1">
        {data?.direct_target ? (
          <ChatRow
            selected={value === data.direct_target}
            onSelect={() => onChange(data.direct_target!)}
            icon={MessageCircle}
            name="Message me directly"
            detail="Sent to your own WhatsApp number"
          />
        ) : null}
        {chats.map((c) => (
          <ChatRow
            key={c.target}
            selected={value === c.target}
            onSelect={() => onChange(c.target)}
            icon={c.type === 'group' ? Users : MessageCircle}
            name={c.name}
            detail={c.type === 'group' ? `Group${c.participants ? ` · ${c.participants} people` : ''}` : 'Direct chat'}
            badge={c.includes_you ? 'You’re in it' : undefined}
          />
        ))}
        {!loading && !chats.length && !data?.direct_target ? (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            {data?.filtered
              ? 'No chats with your number yet. Add your phone number to your profile, or create a WhatsApp group with the jobwright number and refresh.'
              : 'No chats found.'}
          </p>
        ) : null}
        {loading && !data ? (
          <p className="flex items-center justify-center gap-2 px-3 py-6 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Loading chats…
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {hideTest ? null : (
          <Button type="button" size="sm" variant="outline" disabled={!value || testing} onClick={() => void test()}>
            {testing ? <Loader2 className="animate-spin" /> : <Send />} Send a test message
          </Button>
        )}
        <button
          type="button"
          className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          onClick={() => setManual((v) => !v)}
        >
          {manual ? 'Hide chat id' : 'Enter a chat id instead'}
        </button>
      </div>
      {manual ? (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value.trim())}
          placeholder="whatsapp:1203…@g.us"
          className="h-8 font-mono text-xs"
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
}: {
  selected: boolean
  onSelect: () => void
  icon: typeof Users
  name: string
  detail: string
  badge?: string
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
        selected ? 'bg-primary/10' : 'hover:bg-accent/60',
      )}
    >
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{name}</span>
        <span className="block truncate text-xs text-muted-foreground">{detail}</span>
      </span>
      {badge ? <Chip className="shrink-0">{badge}</Chip> : null}
      {selected ? <Check className="size-4 shrink-0 text-primary" aria-hidden /> : null}
    </button>
  )
}

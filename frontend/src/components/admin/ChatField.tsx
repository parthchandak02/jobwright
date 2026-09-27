import { useEffect, useState, type ReactNode } from 'react'
import { MessageCircle, Users } from 'lucide-react'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { Button } from '@/components/ui/button'
import { useDebouncedCallback } from '@/lib/useDebouncedCallback'
import { cn } from '@/lib/utils'

type Props = {
  value: string
  name?: string | null
  type?: 'group' | 'dm' | null
  onCommit: (target: string) => void
  actions?: ReactNode
  emptyLabel?: string
}

/** Current WhatsApp chat as one line; "Change" opens the full picker. Picks save after a short pause. */
export function ChatField({ value, name, type, onCommit, actions, emptyLabel = 'No chat' }: Props) {
  const [picking, setPicking] = useState(false)
  const [draft, setDraft] = useState(value)
  const commit = useDebouncedCallback(onCommit)

  useEffect(() => setDraft(value), [value])

  const Icon = type === 'dm' ? MessageCircle : Users
  const label = draft === value && name ? name.replace(/^whatsapp:/, '') : draft ? draft.replace(/^whatsapp:/, '') : emptyLabel

  return (
    <div className="space-y-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span
          className={cn('flex min-w-0 flex-1 items-center gap-1.5 text-sm', !draft && 'text-muted-foreground')}
          title={draft || undefined}
        >
          {draft ? <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden /> : null}
          <span className="truncate">{label}</span>
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button size="xs" variant="outline" aria-expanded={picking} onClick={() => setPicking((v) => !v)}>
            {picking ? 'Done' : draft ? 'Change' : 'Pick chat'}
          </Button>
          {actions}
        </div>
      </div>
      {picking ? (
        <WhatsAppChatPicker
          hideTest
          value={draft}
          onChange={(t) => {
            setDraft(t)
            commit(t)
          }}
        />
      ) : null}
    </div>
  )
}

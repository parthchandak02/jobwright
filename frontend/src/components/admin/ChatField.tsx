import { useEffect, useState } from 'react'
import { MessageCircle, Users } from 'lucide-react'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { chatDisplay } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { useDebouncedCallback } from '@/lib/useDebouncedCallback'
import { cn } from '@/lib/utils'

type Props = {
  value: string
  name?: string | null
  type?: 'group' | 'dm' | null
  onCommit: (target: string) => void
  emptyLabel?: string
  id?: string
}

/** Current WhatsApp chat as one line; "Change" opens the full picker. Picks save after a short pause. */
export function ChatField({ value, name, type, onCommit, emptyLabel = 'No chat yet', id }: Props) {
  const [picking, setPicking] = useState(false)
  const [draft, setDraft] = useState(value)
  const commit = useDebouncedCallback(onCommit)

  useEffect(() => setDraft(value), [value])

  const shown = draft ? chatDisplay(draft === value ? name : null, draft, draft === value ? type : null) : null
  const Icon = (draft === value ? type : null) === 'dm' ? MessageCircle : Users

  return (
    <div className="space-y-3">
      <div className="flex min-h-11 min-w-0 items-center gap-3 rounded-md border border-border-strong bg-surface px-3 py-1.5 md:min-h-10">
        {shown ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
        <span
          id={id}
          className={cn('min-w-0 flex-1 truncate text-body', (!shown || shown.unnamed) && 'text-muted-foreground')}
          title={draft ? draft.replace(/^whatsapp:/, '') : undefined}
        >
          {shown?.label ?? emptyLabel}
        </span>
        <Button
          size="xs"
          variant="ghost"
          className="-mr-1.5 shrink-0 text-primary"
          aria-expanded={picking}
          onClick={() => setPicking((v) => !v)}
        >
          {picking ? 'Done' : draft ? 'Change' : 'Pick chat'}
        </Button>
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

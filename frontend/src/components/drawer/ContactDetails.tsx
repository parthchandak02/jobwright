import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Copy, UserRound } from 'lucide-react'
import { toast } from 'sonner'
import { DrawerSection } from '@/components/DrawerSection'
import { Button } from '@/components/ui/button'
import { writeClipboardText } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import {
  pickContactDetails,
  type ContactDetailItem,
  type ContactDetailKey,
} from './contactDetails'

type Props = {
  jobKey: string
  personal: Record<string, unknown> | null | undefined
}

/** Collapsed-by-default contact details with one-tap clipboard copy for manual applying. */
export function ContactDetails({ jobKey, personal }: Props) {
  const [open, setOpen] = useState(false)
  const [copiedKey, setCopiedKey] = useState<ContactDetailKey | null>(null)
  const timerRef = useRef<number | undefined>(undefined)

  const items = useMemo(() => pickContactDetails(personal), [personal])

  useEffect(() => {
    setOpen(false)
    setCopiedKey(null)
    window.clearTimeout(timerRef.current)
  }, [jobKey])

  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  if (!items.length) return null

  async function copyItem(item: ContactDetailItem) {
    const ok = await writeClipboardText(item.value)
    if (!ok) {
      toast.error('Copy failed')
      return
    }
    window.clearTimeout(timerRef.current)
    setCopiedKey(item.key)
    toast.success('Copied')
    timerRef.current = window.setTimeout(() => setCopiedKey(null), 1500)
  }

  return (
    <DrawerSection>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => setOpen((v) => !v)}
        className="-ml-3 text-muted-foreground"
        aria-expanded={open}
      >
        <UserRound /> Your details
        <ChevronDown className={cn('transition-transform duration-(--dur-2)', open && 'rotate-180')} />
      </Button>
      {open ? (
        <ul className="surface mt-3 divide-y divide-border rounded-lg border">
          {items.map((item) => {
            const copied = copiedKey === item.key
            return (
              <li key={item.key} className="flex items-center gap-3 py-2 pr-2 pl-3.5">
                <span className="w-24 shrink-0 text-caption text-muted-foreground">{item.label}</span>
                <span className="min-w-0 flex-1 truncate text-body text-foreground" title={item.value}>
                  {item.value}
                </span>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label={copied ? `${item.label} copied` : `Copy ${item.label}`}
                  title={copied ? 'Copied' : `Copy ${item.label}`}
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={() => void copyItem(item)}
                >
                  {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                  <span aria-live="polite" className="sr-only">
                    {copied ? 'Copied' : ''}
                  </span>
                </Button>
              </li>
            )
          })}
        </ul>
      ) : null}
    </DrawerSection>
  )
}

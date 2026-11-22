import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, ClipboardList, Copy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { DrawerSection } from '@/components/DrawerSection'
import { Button } from '@/components/ui/button'
import type { ApplicationAnswers } from '@/lib/api'
import { writeClipboardText } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import { pickMissingAnswers, pickSavedAnswers, type SavedAnswerItem } from './savedAnswers'

type Props = { jobKey: string; data: ApplicationAnswers | null | undefined }

/** Collapsed-by-default read-only saved answers with one-tap clipboard copy for manual applying. */
export function SavedAnswers({ jobKey, data }: Props) {
  const [open, setOpen] = useState(false)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const timerRef = useRef<number | undefined>(undefined)

  const sections = useMemo(() => pickSavedAnswers(data), [data])
  const missing = useMemo(() => pickMissingAnswers(data), [data])

  useEffect(() => {
    setOpen(false)
    setCopiedKey(null)
    window.clearTimeout(timerRef.current)
  }, [jobKey])

  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  if (!sections.length && !missing.length) return null

  async function copyItem(item: SavedAnswerItem) {
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
        type="button" size="sm" variant="ghost"
        onClick={() => setOpen((v) => !v)}
        className="-ml-3 text-muted-foreground" aria-expanded={open}
      >
        <ClipboardList /> Your answers
        <ChevronDown className={cn('transition-transform duration-(--dur-2)', open && 'rotate-180')} />
      </Button>
      {open ? (
        <div className="mt-3 space-y-4">
          {sections.map((section) => (
            <div key={section.id}>
              <h4 className="text-caption font-medium text-muted-foreground">{section.title}</h4>
              <ul className="surface mt-1.5 divide-y divide-border rounded-lg border">
                {section.items.map((item) => {
                  const copied = copiedKey === item.key
                  return (
                    <li key={item.key} className="flex items-center gap-3 py-2 pr-2 pl-3.5">
                      <div className="min-w-0 flex-1">
                        <p className="text-caption text-muted-foreground" title={item.hintLabel}>{item.label}</p>
                        <p className="mt-0.5 break-words text-body text-foreground">{item.value}</p>
                      </div>
                      <Button
                        type="button" size="icon-sm" variant="ghost"
                        aria-label={copied ? `${item.label} copied` : `Copy ${item.label}`}
                        title={copied ? 'Copied' : `Copy ${item.label}`}
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        onClick={() => void copyItem(item)}
                      >
                        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                        <span aria-live="polite" className="sr-only">{copied ? 'Copied' : ''}</span>
                      </Button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
          {missing.length ? (
            <p className="text-caption text-muted-foreground">
              Not saved yet: {missing.join(', ')} ·{' '}
              <Link
                to="/profile?tab=about#application-details"
                className="relative touch-target whitespace-nowrap text-foreground underline decoration-border-strong underline-offset-4 hover:decoration-foreground"
              >
                Add in Settings
              </Link>
            </p>
          ) : null}
          {sections.length ? (
            <div className="flex justify-end">
              <Button asChild size="sm" variant="ghost" className="text-muted-foreground">
                <Link to="/profile?tab=about#application-details">Change in Settings</Link>
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </DrawerSection>
  )
}

import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  /** Show the bar (e.g. when the form is dirty). Defaults to true for always-on footers. */
  open?: boolean
  /** Left text. Defaults to "You have unsaved changes" when `onSave` is set. */
  message?: ReactNode
  onSave?: () => void
  onDiscard?: () => void
  saveLabel?: string
  discardLabel?: string
  saving?: boolean
  saveDisabled?: boolean
  /** Custom actions (right side); replaces the Discard/Save pair. */
  children?: ReactNode
  className?: string
}

/**
 * Sticky bottom bar for the primary action of a view. Place it as the last child of the page's
 * scroll container. Desktop: floating bar in the content column; phone: full-width, safe-area padded.
 */
export function ActionBar({
  open = true,
  message,
  onSave,
  onDiscard,
  saveLabel = 'Save',
  discardLabel = 'Discard',
  saving = false,
  saveDisabled = false,
  children,
  className,
}: Props) {
  if (!open) return null
  const text = message ?? (onSave ? 'You have unsaved changes' : null)

  return (
    <div
      data-slot="action-bar"
      className={cn('sticky bottom-0 z-20 mt-8 max-md:-mx-page-x md:bottom-4', className)}
    >
      <div
        role="region"
        aria-label="Actions"
        className="flex animate-in items-center gap-3 border-t bg-surface px-4 pt-3 pb-[calc(0.75rem+var(--safe-bottom))] shadow-e1 duration-(--dur-2) fade-in-0 slide-in-from-bottom-2 md:rounded-lg md:border md:py-3 md:pr-3"
      >
        {text ? <p className="min-w-0 flex-1 truncate text-caption text-muted-foreground">{text}</p> : <div className="flex-1" />}
        <div className="flex shrink-0 items-center gap-2">
          {children ?? (
            <>
              {onDiscard ? (
                <Button type="button" size="sm" variant="ghost" onClick={onDiscard} disabled={saving}>
                  {discardLabel}
                </Button>
              ) : null}
              {onSave ? (
                <Button type="button" size="sm" onClick={onSave} disabled={saving || saveDisabled}>
                  {saving ? <Loader2 className="animate-spin" /> : null}
                  {saveLabel}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

import { HelpCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** "?" button that opens a longer explanation on click or tap. Prefer a visible FormField `hint` for short help. */
export function FieldHint({
  text,
  label = 'More about this',
  className,
}: {
  text: ReactNode
  label?: string
  className?: string
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'touch-target relative inline-flex size-5 shrink-0 items-center justify-center rounded-full text-subtle-foreground transition-colors duration-(--dur-1) hover:text-foreground data-[state=open]:text-foreground',
            className,
          )}
          aria-label={label}
        >
          <HelpCircle className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="w-auto max-w-xs px-3 py-2 text-caption text-muted-foreground">
        {text}
      </PopoverContent>
    </Popover>
  )
}

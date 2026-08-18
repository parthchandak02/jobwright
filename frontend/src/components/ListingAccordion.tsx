import { cn } from '@/lib/utils'

type Props = {
  description?: string | null
  className?: string
}

export function ListingAccordion({ description, className }: Props) {
  const text = description?.trim()
  if (!text) return null

  return (
    <details className={cn('group rounded-md border border-border/60 bg-muted/20', className)}>
      <summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium text-foreground marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-muted-foreground transition-transform group-open:rotate-90">▸</span>
          Full listing
        </span>
      </summary>
      <div className="max-h-48 overflow-y-auto border-t border-border/50 px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
        {text}
      </div>
    </details>
  )
}

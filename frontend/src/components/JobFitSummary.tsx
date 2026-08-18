import { cn } from '@/lib/utils'

type Props = {
  keywords?: string | null
  reasoning?: string | null
  className?: string
}

/** Prefer a short keyword line; fall back to first sentence of reasoning. */
export function fitSummaryText(keywords?: string | null, reasoning?: string | null): string {
  const kw = keywords?.trim()
  if (kw) return kw
  const reason = reasoning?.trim()
  if (!reason) return ''
  const sentence = reason.split(/(?<=[.!?])\s+/)[0] || reason
  return sentence
}

export function JobFitSummary({ keywords, reasoning, className }: Props) {
  const text = fitSummaryText(keywords, reasoning)
  if (!text) return null
  return (
    <p className={cn('line-clamp-2 text-sm text-muted-foreground', className)}>{text}</p>
  )
}

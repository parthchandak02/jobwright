import { useLayoutEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Job description, collapsed to a fixed height with a "Show full description" toggle. */
export function JobDescriptionPane({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)

  useLayoutEffect(() => {
    setExpanded(false)
  }, [text])

  useLayoutEffect(() => {
    const el = ref.current
    if (el && !expanded) setOverflows(el.scrollHeight > el.clientHeight + 8)
  }, [text, expanded])

  return (
    <div>
      <div
        ref={ref}
        data-collapsed={!expanded ? 'true' : 'false'}
        className="job-drawer-jd materials-preview text-body text-foreground"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
      {overflows || expanded ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="mt-1 -ml-3"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          <ChevronDown className={cn('transition-transform duration-(--dur-2)', expanded && 'rotate-180')} />
          {expanded ? 'Show less' : 'Show full description'}
        </Button>
      ) : null}
    </div>
  )
}

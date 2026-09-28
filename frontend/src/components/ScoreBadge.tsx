import { Pencil } from 'lucide-react'
import { SCORE_LABEL, SCORE_SHORT, scoreLevel, scoreToneStyle } from '@/lib/scoreColor'
import { cn } from '@/lib/utils'

type Props = {
  score: number | null | undefined
  className?: string
  label?: 'none' | 'short' | 'long'
  userModified?: boolean
}

export function ScoreBadge({ score, className, label = 'short', userModified }: Props) {
  const level = scoreLevel(score)
  const tone = scoreToneStyle(score)
  const words = label === 'long' ? SCORE_LABEL[level] : label === 'short' ? SCORE_SHORT[level] : null

  return (
    <span
      data-slot="score"
      title={`${score != null ? `${score}/10 · ` : ''}${SCORE_LABEL[level]}${userModified ? ' (set by you)' : ''}`}
      className={cn(
        'inline-flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-micro whitespace-nowrap tabular-nums',
        tone ? 'tone-tint' : 'border-border bg-surface-muted text-muted-foreground',
        className,
      )}
      style={tone}
    >
      {score != null ? <span className="font-semibold">{score}</span> : null}
      {words ? (
        <>
          {score != null && label === 'long' ? <span aria-hidden>·</span> : null}
          <span className="font-medium">{words}</span>
        </>
      ) : score == null ? (
        <span aria-label="Not scored">–</span>
      ) : null}
      {userModified ? <Pencil className="size-3 opacity-80" aria-label="Set by you" /> : null}
    </span>
  )
}

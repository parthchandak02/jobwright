import { useEffect, useState } from 'react'
import { MessageCircleQuestion } from 'lucide-react'
import { QuestionRow } from '@/components/profile/ClaudeQuestions'
import { listPending, type PendingInput } from '@/lib/api'
import { questionsForJob } from '@/lib/claudeQuestions'

/** Job drawer: questions the person's Claude paused this application on, answered right here. */
export function JobQuestions({ jobId, onAnswered }: { jobId: string; onAnswered: () => void }) {
  const [questions, setQuestions] = useState<PendingInput[]>([])

  useEffect(() => {
    let cancelled = false
    setQuestions([])
    listPending('open', 'answer')
      .then((r) => {
        if (!cancelled) setQuestions(questionsForJob(r.pending, jobId))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [jobId])

  if (!questions.length) return null
  return (
    <section aria-labelledby="job-claude-questions" className="rounded-lg border border-border bg-surface">
      <h3 id="job-claude-questions" className="flex items-center gap-2 border-b border-border px-4 py-2 text-label text-foreground">
        <MessageCircleQuestion className="size-4 shrink-0" style={{ color: 'var(--primary)' }} aria-hidden />
        Your Claude needs {questions.length === 1 ? 'an answer' : `${questions.length} answers`}
      </h3>
      <ul className="divide-y divide-border">
        {questions.map((q) => (
          <QuestionRow
            key={q.id}
            q={q}
            onAnswered={(id) => {
              setQuestions((prev) => prev.filter((p) => p.id !== id))
              onAnswered()
            }}
          />
        ))}
      </ul>
    </section>
  )
}

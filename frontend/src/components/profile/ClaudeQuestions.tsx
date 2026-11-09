import { useState } from 'react'
import { toast } from 'sonner'
import { SectionHeader } from '@/components/SectionHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { providePending, type PendingInput } from '@/lib/api'
import { answerControl, questionGroups } from '@/lib/claudeQuestions'
import { errorMessage } from '@/lib/utils'

function QuestionRow({ q, onAnswered }: { q: PendingInput; onAnswered: (id: string) => void }) {
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const choices = (q.choices ?? []).filter((c) => c.trim())
  const control = answerControl(choices)
  const inputId = `claude-question-${q.id}`

  async function save() {
    if (!value.trim()) return
    setSaving(true)
    try {
      await providePending(q.id, value.trim())
      toast.success('Saved. Your Claude will use it on every form that asks.')
      onAnswered(q.id)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="space-y-2 px-4 py-3">
      <label htmlFor={inputId} className="block text-label text-foreground">
        {q.prompt}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        {control === 'buttons' ? (
          <Segmented
            aria-label={q.prompt}
            value={value}
            onValueChange={(v) => setValue(v)}
            options={choices.map((c) => ({ value: c, label: c }))}
          />
        ) : control === 'select' ? (
          <Select value={value} onValueChange={setValue}>
            <SelectTrigger id={inputId} className="w-full sm:w-80" aria-label={q.prompt}>
              <SelectValue placeholder="Choose your answer" />
            </SelectTrigger>
            <SelectContent>
              {choices.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            id={inputId}
            className="w-full sm:w-80"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void save()
            }}
            placeholder="Write it exactly as it should be given"
          />
        )}
        <Button type="button" size="sm" disabled={!value.trim() || saving} onClick={() => void save()}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </li>
  )
}

/** Settings → About you → Application details: questions the person's own Claude could not answer from their resume or saved answers. */
export function ClaudeQuestions({
  pending,
  onAnswered,
}: {
  pending: PendingInput[]
  onAnswered: (id: string) => void
}) {
  const groups = questionGroups(pending)
  if (!groups.length) return null
  return (
    <section aria-labelledby="claude-questions" className="mb-6">
      <SectionHeader
        id="claude-questions"
        title="Questions from your Claude"
        help="Only you can answer these. Each answer is saved with your application answers, so the next form that asks fills itself."
      />
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.key} className="rounded-lg border border-border">
            <p className="border-b border-border px-4 py-2 text-caption text-muted-foreground">{g.company}</p>
            <ul className="divide-y divide-border">
              {g.questions.map((q) => (
                <QuestionRow key={q.id} q={q} onAnswered={onAnswered} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

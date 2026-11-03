import { DrawerSection } from '@/components/DrawerSection'
import { SaveStatus } from '@/components/SaveStatus'
import { Textarea } from '@/components/ui/textarea'
import type { useJobNotes } from './useJobNotes'

export function JobNotes({ notes, first }: { notes: ReturnType<typeof useJobNotes>; first?: boolean }) {
  return (
    <DrawerSection
      first={first}
      title="Notes"
      actions={<SaveStatus state={notes.state} savedAt={notes.savedAt} onRetry={notes.retry} />}
    >
      <Textarea
        id="notes"
        value={notes.notes}
        rows={3}
        aria-label="Notes"
        placeholder="Write notes for yourself"
        onChange={(e) => notes.onChange(e.target.value)}
        onBlur={notes.flush}
      />
    </DrawerSection>
  )
}

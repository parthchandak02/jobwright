import { useState } from 'react'
import { AutoSearchDialog } from '@/components/AutoSearchDialog'
import { RunProgressButton } from '@/components/RunProgressButton'
import { useAutoSearch, STAGE_LABELS } from '@/lib/useAutoSearch'

type Props = {
  onRunDone: () => void
}

/** Owns Auto Search state so SSE log ticks do not re-render the Kanban board. */
export function AutoSearchControls({ onRunDone }: Props) {
  const [open, setOpen] = useState(false)
  const run = useAutoSearch(onRunDone)

  return (
    <>
      <RunProgressButton
        run={run}
        idleLabel="Auto Search"
        variant="prepare"
        stageLabels={STAGE_LABELS}
        titleIdle="Run auto search. Prepared jobs land in Prepare."
        titleActive="Auto search in progress. Click to view logs"
        onClick={() => {
          run.start()
          setOpen(true)
        }}
      />
      <AutoSearchDialog open={open} onClose={() => setOpen(false)} run={run} />
    </>
  )
}

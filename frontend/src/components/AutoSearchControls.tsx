import { useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { AutoSearchDialog } from '@/components/AutoSearchDialog'
import { RunProgressButton } from '@/components/RunProgressButton'
import { Button } from '@/components/ui/button'
import { useAutoSearch, RUN_STAGE_LABELS } from '@/lib/useAutoSearch'

type Props = {
  onRunDone: () => void
  labelled?: boolean
  /** Desktop shows a plain icon until a run starts, then the progress button (board header). */
  iconOnly?: boolean
}

export function AutoSearchControls({ onRunDone, labelled, iconOnly }: Props) {
  const [open, setOpen] = useState(false)
  const run = useAutoSearch(onRunDone)

  function onClick() {
    run.start()
    setOpen(true)
  }

  return (
    <>
      {labelled ? null : (
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          className={iconOnly && !run.active ? undefined : 'md:hidden'}
          onClick={onClick}
          title={run.active ? undefined : 'Search for new jobs now'}
          aria-label={run.active ? 'Auto Search running. View progress' : 'Run Auto Search'}
        >
          {run.active ? <Loader2 className="animate-spin" /> : <Sparkles />}
        </Button>
      )}
      {iconOnly && !run.active ? null : (
      <RunProgressButton
        run={run}
        idleLabel="Auto Search"
        variant="prepare"
        stageLabels={RUN_STAGE_LABELS}
        titleIdle="Run auto search. Prepared jobs land in Prepare."
        titleActive="Auto search in progress. Click to view logs"
        onClick={onClick}
        className={labelled ? undefined : 'max-md:hidden'}
      />
      )}
      <AutoSearchDialog open={open} onClose={() => setOpen(false)} run={run} />
    </>
  )
}

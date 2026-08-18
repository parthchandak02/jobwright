import { RunProgressDialog } from '@/components/RunProgressDialog'
import { STAGE_LABELS, type AutoSearch } from '@/lib/useAutoSearch'

type Props = {
  open: boolean
  onClose: () => void
  run: AutoSearch
}

export function AutoSearchDialog({ open, onClose, run }: Props) {
  return (
    <RunProgressDialog
      open={open}
      onClose={onClose}
      title="Auto Search"
      description="Full pipeline: discover through connect. Closing this window does not stop the run."
      stageLabels={STAGE_LABELS}
      run={run}
    />
  )
}

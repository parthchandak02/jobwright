import { Columns3, LayoutList } from 'lucide-react'
import { Segmented } from '@/components/ui/segmented'

export type ViewMode = 'board' | 'table'

type Props = {
  value: ViewMode
  onChange: (value: ViewMode) => void
}

const OPTIONS = [
  {
    value: 'board' as const,
    'aria-label': 'Board',
    label: (
      <>
        <Columns3 aria-hidden />
        <span className="board-head-label max-md:sr-only">Board</span>
      </>
    ),
  },
  {
    value: 'table' as const,
    'aria-label': 'Table',
    label: (
      <>
        <LayoutList aria-hidden />
        <span className="board-head-label max-md:sr-only">Table</span>
      </>
    ),
  },
]

/**
 * Board / Table switch. A two-option toggle (radio group), not tabs: it re-renders the one jobs
 * view in place, so there is no separate tab panel for each option.
 */
export function ViewModeTabs({ value, onChange }: Props) {
  return (
    <Segmented
      value={value}
      onValueChange={onChange}
      options={OPTIONS}
      aria-label="Jobs view"
      itemClassName="touch-target relative gap-1.5 [&_svg]:size-4 [&_svg]:shrink-0 max-md:px-3.5"
    />
  )
}

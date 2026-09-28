import { Columns3, LayoutList } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export type ViewMode = 'board' | 'table'

type Props = {
  value: ViewMode
  onChange: (value: ViewMode) => void
}

export function ViewModeTabs({ value, onChange }: Props) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as ViewMode)} className="gap-0">
      <TabsList>
        <TabsTrigger value="board" aria-label="Board" className="touch-target max-md:px-3.5">
          <Columns3 aria-hidden />
          <span className="max-md:sr-only">Board</span>
        </TabsTrigger>
        <TabsTrigger value="table" aria-label="Table" className="touch-target max-md:px-3.5">
          <LayoutList aria-hidden />
          <span className="max-md:sr-only">Table</span>
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}

import { Columns3, LayoutList } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export type ViewMode = 'board' | 'table'

type Props = {
  value: ViewMode
  onChange: (value: ViewMode) => void
}

/** Board / table switcher — matches default TabsList pill style (MaterialsPanel, etc.). */
export function ViewModeTabs({ value, onChange }: Props) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as ViewMode)} className="gap-0">
      <TabsList>
        <TabsTrigger value="board" className="gap-1.5">
          <Columns3 className="size-3.5" />
          Board
        </TabsTrigger>
        <TabsTrigger value="table" className="gap-1.5">
          <LayoutList className="size-3.5" />
          Table
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}

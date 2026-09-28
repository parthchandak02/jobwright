import { SaveStatus } from '@/components/SaveStatus'
import {
  PersonActionBar,
  PersonHealth,
  PersonSettings,
  type PersonActions,
  type SaveState,
} from '@/components/admin/PersonSettings'
import { STATUS_TEXT, StatusDot } from '@/components/admin/StatusDot'
import { STATUS_LABEL, personStatus } from '@/components/admin/adminFormat'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { AdminOverviewUser } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = PersonActions & {
  user: AdminOverviewUser | null
  onClose: () => void
  saveState: SaveState
  savedAt?: number | null
}

/** Phone and tablet: one person's settings in a 92vh bottom sheet with sticky header and actions. */
export function PersonSheet({ user: u, onClose, saveState, savedAt, onPatch, ...actions }: Props) {
  const status = u ? personStatus(u) : 'none'
  return (
    <Sheet open={!!u} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="bottom" className="h-[92dvh] gap-0 pt-3">
        {u ? (
          <>
            <SheetHeader className="border-b px-4 pt-2 pb-3">
              <SheetTitle>{u.name}</SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-x-3">
                <span className={cn('inline-flex items-center gap-2', STATUS_TEXT[status])}>
                  <StatusDot status={status} />
                  {STATUS_LABEL[status]}
                </span>
                <SaveStatus state={saveState ?? 'idle'} savedAt={savedAt} className="min-h-0" />
              </SheetDescription>
            </SheetHeader>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-5 pb-8">
              <div className="mb-8">
                <PersonHealth user={u} />
              </div>
              <PersonSettings id={`sheet-${u.user_id}`} user={u} onPatch={onPatch} onOpen={actions.onOpen} layout="sheet" />
            </div>
            <div className="border-t bg-popover px-4 pt-3 pb-2">
              <PersonActionBar user={u} {...actions} />
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

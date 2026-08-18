import type { LucideIcon } from 'lucide-react'
import {
  Archive,
  ClipboardList,
  Clock,
  Inbox,
  LayoutGrid,
  Send,
  Sparkles,
} from 'lucide-react'

export const NAV_ICONS: Record<string, LucideIcon> = {
  all: LayoutGrid,
  backlog: Inbox,
  prepare: ClipboardList,
  applied: Send,
  in_progress: Clock,
  offer: Sparkles,
  closed: Archive,
}

import { toast } from 'sonner'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { switchProfile } from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'

/** "Alex Rivera" → "AR"; one word → its first letter. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  const letters = parts.length === 1 ? parts[0][0] : parts[0][0] + parts[parts.length - 1][0]
  return letters.toUpperCase()
}

/**
 * Switch between profiles this login may open (admins: all of them). Reloads the app.
 * `variant="sidebar"`: the desktop rail's last row, an initials avatar (always visible, so the rail
 * never jumps) that grows into the name when the rail opens.
 */
export function ProfileSwitcher({
  className,
  onOpenChange,
  variant = 'field',
}: {
  className?: string
  onOpenChange?: (open: boolean) => void
  variant?: 'field' | 'sidebar'
}) {
  const { me } = useMe()
  if (!me || me.profiles.length <= 1) return null
  const active = me.profiles.find((p) => p.user_id === me.active_user)
  const activeName = active?.name || active?.user_id || 'Profile'
  return (
    <Select
      value={me.active_user || undefined}
      onOpenChange={onOpenChange}
      onValueChange={(uid) => {
        void switchProfile(uid)
          .then(() => window.location.assign('/'))
          .catch((e) => toast.error(errorMessage(e)))
      }}
    >
      {variant === 'sidebar' ? (
        <SelectTrigger
          className={cn(
            'h-auto gap-2 border-0 bg-transparent px-2.5 py-1.5 text-body hover:bg-sidebar-accent/60 md:h-auto md:text-body',
            className,
          )}
          aria-label={`Switch profile (now ${activeName})`}
          title="Switch profile"
        >
          <span
            aria-hidden
            className="flex size-6 -mx-0.5 shrink-0 items-center justify-center rounded-full bg-accent text-micro leading-none font-semibold text-accent-foreground"
          >
            {initials(activeName)}
          </span>
          <span className="sidebar-label min-w-0 flex-1 text-left">
            <SelectValue placeholder="Profile" />
          </span>
        </SelectTrigger>
      ) : (
        <SelectTrigger className={className} aria-label="Switch profile">
          <SelectValue placeholder="Profile" />
        </SelectTrigger>
      )}
      <SelectContent>
        {me.profiles.map((p) => (
          <SelectItem key={p.user_id} value={p.user_id}>
            {p.name || p.user_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

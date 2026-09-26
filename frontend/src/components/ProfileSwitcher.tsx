import { toast } from 'sonner'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { switchProfile } from '@/lib/api'
import { useMe } from '@/lib/me'
import { errorMessage } from '@/lib/utils'

/** Switch between profiles this login may open (admins: all of them). Reloads the app. */
export function ProfileSwitcher({ className }: { className?: string }) {
  const { me } = useMe()
  if (!me || me.profiles.length <= 1) return null
  return (
    <Select
      value={me.active_user || undefined}
      onValueChange={(uid) => {
        void switchProfile(uid)
          .then(() => window.location.assign('/'))
          .catch((e) => toast.error(errorMessage(e)))
      }}
    >
      <SelectTrigger className={className} aria-label="Switch profile">
        <SelectValue placeholder="Profile" />
      </SelectTrigger>
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

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { apiFetch, Profile } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type UserOption = { user_id: string; name: string }

type Props = {
  profile: Profile | null
  onChanged: () => void
}

export function UserSwitcher({ profile, onChanged }: Props) {
  const [users, setUsers] = useState<UserOption[]>([])

  useEffect(() => {
    void apiFetch<{ users: UserOption[] }>('/users')
      .then((r) => setUsers(r.users || []))
      .catch(() => setUsers([]))
  }, [])

  if (users.length <= 1) {
    return (
      <p className="truncate text-xs text-muted-foreground">
        {profile?.name || profile?.user_id || '…'}
      </p>
    )
  }

  return (
    <Select
      value={profile?.user_id || undefined}
      onValueChange={(userId) => {
        void (async () => {
          try {
            await apiFetch<Profile>('/session', {
              method: 'POST',
              body: JSON.stringify({ user_id: userId }),
            })
            onChanged()
            toast.success(`Switched to ${userId}`)
          } catch (e) {
            toast.error(errorMessage(e))
          }
        })()
      }}
    >
      <SelectTrigger className="h-7 w-full border-0 bg-transparent px-0 shadow-none focus-visible:ring-0">
        <SelectValue placeholder="Profile" />
      </SelectTrigger>
      <SelectContent>
        {users.map((u) => (
          <SelectItem key={u.user_id} value={u.user_id}>
            {u.name || u.user_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

import { useState } from 'react'
import { toast } from 'sonner'
import { FormField } from '@/components/FormField'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
import { ApplicationDetails } from '@/components/profile/ApplicationDetails'
import { useAutosave } from '@/components/profile/useAutosave'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { apiFetch, type SettingsProfile } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Field = {
  key: string
  label: string
  hint?: string
  type?: string
  autoComplete?: string
  inputMode?: 'email' | 'tel' | 'url' | 'text'
}

const CONTACT: Field[] = [
  { key: 'full_name', label: 'Full name', autoComplete: 'name' },
  { key: 'email', label: 'Email', type: 'email', autoComplete: 'email', inputMode: 'email' },
  {
    key: 'phone',
    label: 'Phone',
    type: 'tel',
    autoComplete: 'tel',
    inputMode: 'tel',
    hint: 'With country code, like +1. We use it to find your WhatsApp chats.',
  },
]

// City, state, address, ZIP, country and links are edited in Application details below (same saved
// values, one place each). This form sends only its own fields, so it never overwrites those.
const OWN_KEYS = CONTACT.map((f) => f.key)

type Value = { personal: Record<string, string>; target: string }

type Props = {
  profile: SettingsProfile
  onSaved: () => void
  onOpenRules: () => void
}

export function AboutTab({ profile, onSaved, onOpenRules }: Props) {
  const [v, setV] = useState<Value>(() => ({
    personal: profile.personal || {},
    target: profile.experience?.target_role || '',
  }))

  const autosave = useAutosave(
    (value: Value) =>
      apiFetch('/settings/profile', {
        method: 'PUT',
        body: JSON.stringify({
          personal: Object.fromEntries(OWN_KEYS.map((k) => [k, value.personal[k] ?? ''])),
          experience: { target_role: value.target },
        }),
      }),
    { onSaved: () => onSaved(), onError: (e) => toast.error(errorMessage(e)) },
  )

  function patch(p: Partial<Value>) {
    const next = { ...v, ...p }
    setV(next)
    autosave.schedule(next)
  }

  function field(f: Field) {
    return (
      <FormField key={f.key} label={f.label} htmlFor={`about-${f.key}`} help={f.hint}>
        <Input
          id={`about-${f.key}`}
          type={f.type ?? 'text'}
          inputMode={f.inputMode}
          autoComplete={f.autoComplete}
          value={v.personal[f.key] || ''}
          onChange={(e) => patch({ personal: { ...v.personal, [f.key]: e.target.value } })}
        />
      </FormField>
    )
  }

  return (
    <div>
      <SectionHeader
        title="About you"
        help="Used on your applications and when we write your materials. Changes save automatically."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <div className="space-y-field">
        {CONTACT.map(field)}
      </div>

      <SectionHeader title="Your goal" />
      <FormField
        label="Roles you’re aiming for"
        htmlFor="about-target-role"
        help={
          <>
            A sentence or two. We use it on applications and to pick which contacts to suggest. How jobs are scored is set
            in{' '}
            <Button type="button" variant="link" className="h-auto p-0 text-caption" onClick={onOpenRules}>
              Match rules
            </Button>
            .
          </>
        }
      >
        <Textarea
          id="about-target-role"
          value={v.target}
          rows={2}
          onChange={(e) => patch({ target: e.target.value })}
          placeholder="Describe the roles you want"
        />
      </FormField>

      <ApplicationDetails />
    </div>
  )
}

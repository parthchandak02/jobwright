import { useState } from 'react'
import { toast } from 'sonner'
import { FormField } from '@/components/FormField'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
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
    hint: 'Include your country code, like +1. We use it to find your WhatsApp chats.',
  },
]

const PLACE: Field[] = [
  { key: 'city', label: 'City', autoComplete: 'address-level2' },
  { key: 'province_state', label: 'State', autoComplete: 'address-level1' },
]

const LINKEDIN: Field = {
  key: 'linkedin_url',
  label: 'LinkedIn profile',
  type: 'url',
  inputMode: 'url',
  autoComplete: 'url',
  hint: 'The full link to your LinkedIn page.',
}

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
        body: JSON.stringify({ personal: value.personal, experience: { target_role: value.target } }),
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
      <FormField key={f.key} label={f.label} htmlFor={`about-${f.key}`} hint={f.hint}>
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
        description="Used on your applications and when we write your materials. Changes save automatically."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <div className="space-y-field">
        {CONTACT.map(field)}
        <div className="grid grid-cols-[1fr_7rem] gap-3 sm:grid-cols-2 sm:gap-4">{PLACE.map(field)}</div>
        {field(LINKEDIN)}
      </div>

      <SectionHeader title="Your goal" />
      <FormField
        label="Roles you’re aiming for"
        htmlFor="about-target-role"
        hint={
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
    </div>
  )
}

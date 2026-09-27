import { ArrowRight, Loader2 } from 'lucide-react'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  name: string
  onName: (v: string) => void
  phone: string
  onPhone: (v: string) => void
  busy: boolean
  onContinue: () => void
}

export function StepAbout({ name, onName, phone, onPhone, busy, onContinue }: Props) {
  return (
    <WelcomeStep
      title="Let’s set up your job search"
      description="Every morning jobwright finds new roles, checks how well each one fits you, and sends the best to WhatsApp. Setup takes about five minutes."
      onSubmit={() => {
        if (name.trim() && !busy) onContinue()
      }}
      actions={
        <Button type="submit" size="sm" disabled={!name.trim() || busy}>
          {busy ? <Loader2 className="animate-spin" /> : null}
          Continue
          {busy ? null : <ArrowRight />}
        </Button>
      }
    >
      <div className="space-y-field">
        <FormField label="Your name">
          <Input
            value={name}
            onChange={(e) => onName(e.target.value)}
            placeholder="First and last name"
            autoComplete="name"
            autoFocus
          />
        </FormField>
        <FormField
          label="WhatsApp number"
          optional
          hint="Include the country code. It helps connect your daily list to the right chat, and it’s never shared."
        >
          <Input
            value={phone}
            onChange={(e) => onPhone(e.target.value)}
            placeholder="Start with + and your country code"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
          />
        </FormField>
      </div>
    </WelcomeStep>
  )
}

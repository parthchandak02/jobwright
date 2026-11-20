import { useState, type FormEvent } from 'react'
import { Link2 } from 'lucide-react'
import { toast } from 'sonner'
import { Callout } from '@/components/drawer/Callout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { saveApplicationUrl, type JobCard } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/** Open posting only reaches LinkedIn: paste the employer's own apply link so it goes to the real form. */
export function EmployerLinkCallout({ job, onSaved }: { job: JobCard; onSaved: (job: JobCard) => void }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    setBusy(true)
    try {
      onSaved(await saveApplicationUrl(job, value.trim()))
      setValue('')
      toast.success('Open posting now goes to the employer.')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Callout icon={Link2}>
      <form className="flex flex-col gap-2" onSubmit={(e) => void save(e)}>
        <label htmlFor="employer-apply-link">Only a LinkedIn link. Paste the employer&apos;s apply link.</label>
        <div className="flex gap-2">
          <Input
            id="employer-apply-link"
            type="url"
            inputMode="url"
            value={value}
            disabled={busy}
            placeholder="https://careers.example.com/…"
            autoComplete="off"
            onChange={(e) => setValue(e.target.value)}
          />
          <Button type="submit" size="sm" variant="secondary" disabled={busy || !value.trim()}>
            Save
          </Button>
        </div>
      </form>
    </Callout>
  )
}

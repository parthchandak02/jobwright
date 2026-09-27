import { useState } from 'react'
import { Loader2, MessageCircle, Send, Users } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { sendWhatsAppTest } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  target?: string
  name?: string
  className?: string
  /** Hide "Send test" (e.g. during onboarding, so setup never posts to a real chat). */
  hideTest?: boolean
}

/** Read-only view of the WhatsApp chat an admin connected for this profile. */
export function ConnectedChat({ target, name, className, hideTest }: Props) {
  const [testing, setTesting] = useState(false)
  const isGroup = Boolean(target?.endsWith('@g.us'))
  const Icon = isGroup ? Users : MessageCircle

  async function test() {
    setTesting(true)
    try {
      await sendWhatsAppTest('')
      toast.success('Test message sent. Check WhatsApp.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setTesting(false)
    }
  }

  if (!target) {
    return (
      <p className={cn('rounded-lg border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground', className)}>
        Your WhatsApp chat isn’t connected yet. Your admin will set it up; nothing to do on your side.
      </p>
    )
  }
  return (
    <div className={cn('flex flex-wrap items-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2', className)}>
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{name || 'Connected chat'}</span>
      {hideTest ? null : (
        <Button size="sm" variant="outline" onClick={() => void test()} disabled={testing}>
          {testing ? <Loader2 className="animate-spin" /> : <Send />} Send test
        </Button>
      )}
    </div>
  )
}

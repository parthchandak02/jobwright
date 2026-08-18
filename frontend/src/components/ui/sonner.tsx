import { useTheme } from '@/lib/theme'
import { Toaster as Sonner, type ToasterProps } from 'sonner'

function Toaster(props: ToasterProps) {
  const { resolved } = useTheme()
  return (
    <Sonner
      theme={resolved}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: 'border border-border bg-popover text-popover-foreground shadow-md',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }

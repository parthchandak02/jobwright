import { useTheme } from '@/lib/theme'
import { Toaster as Sonner, type ToasterProps } from 'sonner'

function Toaster(props: ToasterProps) {
  const { theme } = useTheme()
  return (
    <Sonner
      theme={theme}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: 'rounded-popover border border-border bg-popover text-popover-foreground shadow-e1',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }

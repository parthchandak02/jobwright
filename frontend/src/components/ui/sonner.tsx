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
          toast: 'border border-border bg-popover text-popover-foreground shadow-md',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }

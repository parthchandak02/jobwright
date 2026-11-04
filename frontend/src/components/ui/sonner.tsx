import { useActionBarShown } from '@/lib/actionBarPresence'
import { useTheme } from '@/lib/theme'
import { Toaster as Sonner, type ToasterProps } from 'sonner'

/** Sonner's default gap from the window edge on desktop. */
const EDGE = '24px'
/** Height of a sticky ActionBar (bulk selection, unsaved changes) plus its gap. */
const BAR = '5rem'

type Props = Omit<ToasterProps, 'offset' | 'mobileOffset'> & {
  /** Phones: distance from the bottom (e.g. above the tab bar). */
  phoneBottom?: string
}

/** Toasts stay clear of a sticky ActionBar while one is shown, on desktop and phone. */
function Toaster({ phoneBottom, ...props }: Props) {
  const { theme } = useTheme()
  const barShown = useActionBarShown()
  const lift = (base: string) => (barShown ? `calc(${base} + ${BAR})` : base)
  return (
    <Sonner
      theme={theme}
      className="toaster group"
      offset={{ bottom: lift(EDGE) }}
      mobileOffset={phoneBottom ? { bottom: lift(phoneBottom) } : undefined}
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

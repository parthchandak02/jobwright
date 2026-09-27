import * as React from 'react'
import { cn } from '@/lib/utils'

const controlBase =
  'w-full min-w-0 rounded-md border border-input bg-surface text-base text-foreground transition-[color,border-color,box-shadow] duration-(--dur-1) ease-out placeholder:text-subtle-foreground hover:border-[color-mix(in_oklch,var(--border-strong),var(--foreground)_12%)] focus-visible:border-primary focus-visible:outline-offset-0 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-subtle-foreground aria-invalid:border-destructive md:text-sm'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        controlBase,
        'h-11 px-3 file:mr-3 file:border-0 file:bg-transparent file:text-label file:text-foreground md:h-10',
        className,
      )}
      {...props}
    />
  )
}

export { Input, controlBase }

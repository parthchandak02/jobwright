import * as React from 'react'
import { Switch as SwitchPrimitive } from 'radix-ui'
import { cn } from '@/lib/utils'

function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'peer touch-target relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full bg-border-strong p-0.5 transition-colors duration-(--dur-2) ease-out disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary md:h-5 md:w-9',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-5 rounded-full bg-surface shadow-e1 ring-0 transition-transform duration-(--dur-2) ease-out data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0 md:size-4 dark:data-[state=checked]:bg-primary-foreground"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }

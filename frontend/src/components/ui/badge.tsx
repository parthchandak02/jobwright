import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border px-2 py-0.5 text-micro font-medium whitespace-nowrap tabular-nums [&>svg]:size-3',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-surface-muted text-foreground',
        destructive: 'tone-tint [--tone:var(--destructive)]',
        outline: 'border-border text-muted-foreground',
        success: 'tone-tint [--tone:var(--success)]',
        warning: 'tone-tint [--tone:var(--warning)]',
        info: 'tone-tint [--tone:var(--primary)]',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }

import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { Slot } from '@radix-ui/react-slot'
import { cn } from '@/lib/utils'

const primary = 'bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/85'
const secondary =
  'border border-border-strong bg-surface text-foreground hover:bg-surface-muted aria-expanded:bg-surface-muted'

const buttonVariants = cva(
  "relative inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-label whitespace-nowrap transition-[color,background-color,border-color,box-shadow,opacity] duration-(--dur-1) ease-out disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary,
        default: primary,
        secondary,
        outline: secondary,
        ghost: 'text-foreground hover:bg-surface-muted aria-expanded:bg-surface-muted',
        destructive: 'bg-destructive text-white hover:bg-destructive/90 dark:text-background',
        'destructive-ghost': 'text-destructive hover:bg-destructive/10',
        link: 'text-primary underline-offset-4 hover:underline',
        ai: 'border border-primary/20 bg-accent text-accent-foreground hover:bg-primary/15',
      },
      size: {
        default: 'h-11 px-4 has-[>svg]:px-3.5 md:h-10',
        xs: 'touch-target h-8 gap-1 px-2.5 text-micro has-[>svg]:px-2 md:h-7',
        sm: 'h-11 gap-1.5 px-3.5 has-[>svg]:px-3 md:h-9 md:px-3 md:has-[>svg]:px-2.5',
        lg: 'h-12 px-6 has-[>svg]:px-5 md:h-11',
        icon: 'size-11 md:size-10',
        'icon-sm': 'touch-target size-9 md:size-8',
      },
    },
    defaultVariants: { variant: 'primary', size: 'default' },
  },
)

type ButtonProps = React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp
      data-slot="button"
      data-variant={variant ?? 'primary'}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants, type ButtonProps }

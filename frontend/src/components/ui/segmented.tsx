import * as React from 'react'
import { ToggleGroup as ToggleGroupPrimitive } from 'radix-ui'
import { cn } from '@/lib/utils'

type Option<T extends string> = { value: T; label: React.ReactNode; disabled?: boolean }

type SegmentedProps<T extends string> = {
  value: T
  onValueChange: (value: T) => void
  options: Option<T>[]
  size?: 'sm' | 'md'
  className?: string
  'aria-label': string
  disabled?: boolean
}

function Segmented<T extends string>({
  value,
  onValueChange,
  options,
  size = 'md',
  className,
  disabled,
  ...aria
}: SegmentedProps<T>) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      data-slot="segmented"
      value={value}
      disabled={disabled}
      onValueChange={(next) => {
        if (next) onValueChange(next as T)
      }}
      className={cn(
        'inline-flex w-fit items-center rounded-md bg-surface-muted p-[3px]',
        size === 'sm' ? 'h-9 md:h-7' : 'h-10 md:h-9',
        className,
      )}
      {...aria}
    >
      {options.map((opt) => (
        <ToggleGroupPrimitive.Item
          key={opt.value}
          value={opt.value}
          disabled={opt.disabled}
          className={cn(
            'inline-flex h-full items-center justify-center rounded-[calc(var(--radius)-4px)] whitespace-nowrap text-muted-foreground transition-[color,background-color,box-shadow] duration-(--dur-1) ease-out hover:text-foreground disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-pill-active data-[state=on]:text-foreground data-[state=on]:shadow-e1',
            size === 'sm' ? 'px-2.5 text-micro' : 'px-3 text-label',
          )}
        >
          {opt.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  )
}

export { Segmented, type SegmentedProps }

import * as React from 'react'
import { Tabs as TabsPrimitive } from 'radix-ui'
import { cn } from '@/lib/utils'

function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn('flex flex-col gap-2', className)} {...props} />
}

type TabsListProps = React.ComponentProps<typeof TabsPrimitive.List> & {
  variant?: 'pill' | 'underline'
}

function useScrollFade(ref: React.RefObject<HTMLDivElement | null>, enabled: boolean) {
  React.useEffect(() => {
    const el = ref.current
    if (!el || !enabled) return
    const update = () => {
      el.dataset.fadeStart = el.scrollLeft > 2 ? 'true' : 'false'
      el.dataset.fadeEnd = el.scrollLeft + el.clientWidth < el.scrollWidth - 2 ? 'true' : 'false'
    }
    const revealActive = () => {
      const active = el.querySelector<HTMLElement>('[data-state="active"]')
      if (!active) return
      const box = el.getBoundingClientRect()
      const rect = active.getBoundingClientRect()
      const left = rect.left - box.left + el.scrollLeft
      const right = left + rect.width
      const pad = 24
      if (left - pad < el.scrollLeft) el.scrollTo({ left: Math.max(0, left - pad), behavior: 'smooth' })
      else if (right + pad > el.scrollLeft + el.clientWidth)
        el.scrollTo({ left: right + pad - el.clientWidth, behavior: 'smooth' })
    }
    update()
    revealActive()
    el.addEventListener('scroll', update, { passive: true })
    const resize = new ResizeObserver(update)
    resize.observe(el)
    const mutations = new MutationObserver(() => {
      revealActive()
      update()
    })
    mutations.observe(el, { subtree: true, attributes: true, attributeFilter: ['data-state'] })
    return () => {
      el.removeEventListener('scroll', update)
      resize.disconnect()
      mutations.disconnect()
    }
  }, [ref, enabled])
}

function TabsList({ className, variant = 'pill', children, ...props }: TabsListProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null)
  useScrollFade(scrollRef, variant === 'underline')

  if (variant === 'underline') {
    return (
      <div
        ref={scrollRef}
        className="scroll-fade-x scrollbar-none -mx-1 overflow-x-auto overscroll-x-contain px-1"
        data-slot="tabs-scroller"
      >
        <TabsPrimitive.List
          data-slot="tabs-list"
          data-variant="underline"
          className={cn(
            'group/tabs-list flex w-max min-w-full items-stretch gap-6 border-b border-border text-muted-foreground',
            className,
          )}
          {...props}
        >
          {children}
        </TabsPrimitive.List>
      </div>
    )
  }

  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant="pill"
      className={cn(
        'group/tabs-list inline-flex h-10 w-fit items-center justify-center rounded-md bg-surface-muted p-[3px] text-muted-foreground md:h-9',
        className,
      )}
      {...props}
    >
      {children}
    </TabsPrimitive.List>
  )
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        'relative inline-flex items-center justify-center gap-1.5 text-label whitespace-nowrap transition-[color,background-color,box-shadow] duration-(--dur-2) ease-out hover:text-foreground disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
        'group-data-[variant=pill]/tabs-list:h-full group-data-[variant=pill]/tabs-list:flex-1 group-data-[variant=pill]/tabs-list:rounded-[calc(var(--radius)-4px)] group-data-[variant=pill]/tabs-list:px-3 group-data-[variant=pill]/tabs-list:data-[state=active]:bg-pill-active group-data-[variant=pill]/tabs-list:data-[state=active]:text-foreground group-data-[variant=pill]/tabs-list:data-[state=active]:shadow-e1',
        'group-data-[variant=underline]/tabs-list:h-11 group-data-[variant=underline]/tabs-list:shrink-0 group-data-[variant=underline]/tabs-list:px-0.5 group-data-[variant=underline]/tabs-list:focus-visible:outline-offset-[-2px] group-data-[variant=underline]/tabs-list:after:absolute group-data-[variant=underline]/tabs-list:after:inset-x-0 group-data-[variant=underline]/tabs-list:after:-bottom-px group-data-[variant=underline]/tabs-list:after:h-0.5 group-data-[variant=underline]/tabs-list:after:rounded-full group-data-[variant=underline]/tabs-list:after:bg-transparent group-data-[variant=underline]/tabs-list:after:transition-colors group-data-[variant=underline]/tabs-list:data-[state=active]:text-foreground group-data-[variant=underline]/tabs-list:data-[state=active]:after:bg-primary',
        className,
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="tabs-content" className={cn('flex-1 outline-none', className)} {...props} />
}

export { Tabs, TabsList, TabsTrigger, TabsContent, type TabsListProps }

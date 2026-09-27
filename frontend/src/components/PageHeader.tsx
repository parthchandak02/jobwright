import type { ReactNode } from 'react'
import { MobileNavTrigger } from '@/components/MobileNav'
import { cn } from '@/lib/utils'

export type PageWidth = 'form' | 'wide' | 'full'

const WIDTH: Record<PageWidth, string> = {
  form: 'max-w-form',
  wide: 'max-w-wide',
  full: '',
}

/** Centred content column with page side padding. `form` 720px, `wide` 960px, `full` no cap. */
export function PageColumn({
  width = 'form',
  className,
  children,
}: {
  width?: PageWidth
  className?: string
  children: ReactNode
}) {
  return (
    <div className="px-page-x">
      <div className={cn('mx-auto w-full', WIDTH[width], className)}>{children}</div>
    </div>
  )
}

type PageHeaderProps = {
  title: ReactNode
  /** One line under the title. */
  description?: ReactNode
  /** Right-aligned actions on desktop (max 2). Also shown in the phone bar unless `mobileActions` is set. */
  actions?: ReactNode
  /** Phone bar actions (at most one or two icon buttons). Pass `null` to hide actions on phone. */
  mobileActions?: ReactNode
  width?: PageWidth
  /** Content under the title block, e.g. underline Tabs. */
  children?: ReactNode
  className?: string
}

/**
 * Page title block. On phone it also renders a sticky 56px bar (menu button, title, actions);
 * place it as the first child of the page's scroll container.
 */
export function PageHeader({
  title,
  description,
  actions,
  mobileActions,
  width = 'form',
  children,
  className,
}: PageHeaderProps) {
  const phoneActions = mobileActions === undefined ? actions : mobileActions
  return (
    <>
      <div
        data-slot="page-bar"
        className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-1 border-b bg-background px-2 md:hidden"
      >
        <MobileNavTrigger />
        <h1 className="min-w-0 flex-1 truncate px-1 text-heading text-foreground">{title}</h1>
        {phoneActions ? <div className="flex shrink-0 items-center gap-1">{phoneActions}</div> : null}
      </div>
      <header data-slot="page-header" className={cn('pt-page-top', className)}>
        <PageColumn width={width}>
          {description || actions ? (
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="hidden text-title text-foreground md:block">{title}</h1>
                {description ? (
                  <p className="text-caption text-muted-foreground md:mt-1.5 md:text-body">{description}</p>
                ) : null}
              </div>
              {actions ? <div className="hidden shrink-0 items-center gap-2 md:flex">{actions}</div> : null}
            </div>
          ) : (
            <h1 className="hidden text-title text-foreground md:block">{title}</h1>
          )}
          {children ? <div className="mt-6">{children}</div> : null}
        </PageColumn>
      </header>
    </>
  )
}

type PageProps = Omit<PageHeaderProps, 'children' | 'className'> & {
  /** Content between the title block and the page body (e.g. underline Tabs list). */
  headerExtra?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

/** Full page shell for non-board routes: own scroll container, PageHeader, content column. */
export function Page({ headerExtra, children, className, bodyClassName, width = 'form', ...header }: PageProps) {
  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col', className)}>
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <PageHeader width={width} {...header}>
          {headerExtra}
        </PageHeader>
        <PageColumn width={width} className={cn('pt-6 pb-16 md:pt-8', bodyClassName)}>
          {children}
        </PageColumn>
      </main>
    </div>
  )
}

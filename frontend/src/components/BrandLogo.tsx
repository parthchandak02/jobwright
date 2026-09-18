import { cn } from '@/lib/utils'

type Props = {
  className?: string
  title?: string
}

/** Shared top-bar height for sidebar brand + main header (56px).
 *  Mobile: auto height + wrap so toolbar buttons stack instead of overflowing
 *  the fixed 56px box and painting over the board. */
export const APP_SHELL_HEADER_HEIGHT =
  'flex min-h-14 max-md:h-auto max-md:flex-wrap max-md:py-2 shrink-0 items-center gap-3 px-4 md:h-14'

export const APP_SHELL_HEADER = `${APP_SHELL_HEADER_HEIGHT} app-shell-header`

/**
 * jobwright mark (option 3, simplified): doc + check, stroke-only.
 * Uses currentColor so it sits cleanly on the sidebar without a badge box.
 */
export function BrandLogo({ className, title = 'jobwright' }: Props) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      className={cn('shrink-0 text-current', className)}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="8" y="6" width="16" height="20" rx="2.5" strokeWidth="2" />
      <path d="M11.5 11.5h9" strokeWidth="2" />
      <path d="M11.5 16h6" strokeWidth="2" opacity="0.55" />
      <path d="M17.5 21.5l2 2 4.5-4.5" strokeWidth="2" />
    </svg>
  )
}

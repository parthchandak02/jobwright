import { Skeleton } from '@/components/ui/skeleton'

/** Placeholder while a lazily loaded page downloads (settings-style layout). */
export function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading page" className="min-w-0 flex-1 px-page-x pt-page-top">
      <div className="mx-auto w-full max-w-form space-y-field">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72 max-w-full" />
        <div className="space-y-3 pt-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  )
}

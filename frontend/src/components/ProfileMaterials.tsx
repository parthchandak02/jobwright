import { useState, type DragEvent, type ReactNode } from 'react'
import { ChevronDown, FileText, Loader2, MoreHorizontal, Trash2, Upload } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { ResumePreview } from '@/components/ResumePreview'
import { SectionHeader } from '@/components/SectionHeader'
import { ConfirmAction } from '@/components/profile/ConfirmAction'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { CoverLetterExample } from '@/lib/api'
import { cn } from '@/lib/utils'

type ResumeSlot = {
  pdfUrl: string | null
  markdown: string
  /** Epoch seconds of the stored PDF. */
  updatedAt?: number | null
  replacing?: boolean
  onReplace: () => void
}

type Props = {
  resume: ResumeSlot
  examples: CoverLetterExample[]
  uploading?: boolean
  onAddCovers: () => void
  onDropCovers?: (files: File[]) => void
  onRemoveCover: (id: string) => Promise<unknown> | void
}

const RESUME = 'resume'

function displayName(example: CoverLetterExample): string {
  return example.filename.replace(/\.(pdf|txt)$/i, '').replaceAll('_', ' ')
}

function fmtDate(epochSeconds: number | null | undefined): string | null {
  if (!epochSeconds) return null
  const d = new Date(epochSeconds * 1000)
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) })
}

function coverPdfUrl(example: CoverLetterExample): string | null {
  return example.kind !== 'txt'
    ? `/api/settings/cover-letters/${encodeURIComponent(example.id)}/pdf?t=${example.mtime}`
    : null
}

export function ProfileMaterials({ resume, examples, uploading, onAddCovers, onDropCovers, onRemoveCover }: Props) {
  const [open, setOpen] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [removing, setRemoving] = useState<CoverLetterExample | null>(null)
  const toggle = (id: string) => setOpen((cur) => (cur === id ? null : id))
  const hasResume = Boolean(resume.pdfUrl || resume.markdown.trim())
  const updated = fmtDate(resume.updatedAt)

  const dropProps = onDropCovers
    ? {
        onDragOver: (e: DragEvent) => {
          if (!e.dataTransfer.types.includes('Files')) return
          e.preventDefault()
          setDragging(true)
        },
        onDragLeave: (e: DragEvent) => {
          if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
          setDragging(false)
        },
        onDrop: (e: DragEvent) => {
          e.preventDefault()
          setDragging(false)
          const files = [...e.dataTransfer.files]
          if (files.length) onDropCovers(files)
        },
      }
    : {}

  return (
    <div>
      <SectionHeader
        title="Resume"
        description="We score every job against your resume and tailor it for strong matches."
      />
      {hasResume ? (
        <ul className="overflow-hidden rounded-lg border bg-surface">
          <DocRow
            title="Resume"
            meta={resume.pdfUrl ? (updated ? `PDF · Updated ${updated}` : 'PDF') : 'Text only · add a PDF for the best results'}
            expanded={open === RESUME}
            onToggle={() => toggle(RESUME)}
            actions={
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={resume.replacing}
                onClick={resume.onReplace}
              >
                {resume.replacing ? <Loader2 className="animate-spin" /> : <Upload />}
                {resume.replacing ? 'Uploading…' : resume.pdfUrl ? 'Replace' : 'Add PDF'}
              </Button>
            }
          >
            <ResumePreview pdfUrl={resume.pdfUrl} markdown={resume.markdown} />
          </DocRow>
        </ul>
      ) : (
        <div className="rounded-lg border border-dashed border-border-strong">
          <EmptyState
            icon={FileText}
            title="No resume yet"
            description="Upload your resume as a PDF. We use it to score jobs and write your materials."
            action={
              <Button type="button" onClick={resume.onReplace} disabled={resume.replacing}>
                {resume.replacing ? <Loader2 className="animate-spin" /> : <Upload />}
                {resume.replacing ? 'Uploading…' : 'Upload resume'}
              </Button>
            }
          />
        </div>
      )}

      <SectionHeader
        title="Cover letter examples"
        description="We follow the tone and structure of these when we write your cover letters. Two or three is plenty."
        actions={
          examples.length ? (
            <Button type="button" size="sm" variant="secondary" disabled={uploading} onClick={onAddCovers}>
              {uploading ? <Loader2 className="animate-spin" /> : <Upload />}
              {uploading ? 'Uploading…' : 'Add letters'}
            </Button>
          ) : null
        }
      />
      <div
        {...dropProps}
        className={cn(
          'rounded-lg transition-[background-color,box-shadow] duration-(--dur-1)',
          dragging && 'bg-accent ring-2 ring-primary/40',
        )}
      >
        {examples.length ? (
          <>
            <ul className="divide-y divide-border overflow-hidden rounded-lg border bg-surface">
              {examples.map((example) => (
                <DocRow
                  key={example.id}
                  title={displayName(example)}
                  meta={`${example.kind === 'txt' ? 'Text' : 'PDF'}${fmtDate(example.mtime) ? ` · Added ${fmtDate(example.mtime)}` : ''}`}
                  expanded={open === example.id}
                  onToggle={() => toggle(example.id)}
                  actions={
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          className="text-muted-foreground"
                          aria-label={`Options for ${displayName(example)}`}
                          disabled={uploading}
                        >
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem variant="destructive" onSelect={() => setRemoving(example)}>
                          <Trash2 />
                          Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  }
                >
                  <ResumePreview
                    pdfUrl={coverPdfUrl(example)}
                    markdown={example.markdown}
                    pdfTitle={`${example.filename} preview`}
                  />
                </DocRow>
              ))}
            </ul>
            {onDropCovers ? (
              <p className="mt-2 hidden text-caption text-muted-foreground md:block">You can also drop PDFs here.</p>
            ) : null}
          </>
        ) : (
          <div className="rounded-lg border border-dashed border-border-strong">
            <EmptyState
              icon={Upload}
              title="No cover letters yet"
              description={onDropCovers ? 'Drop PDFs here, or choose them from your computer.' : 'Add PDFs of letters you’ve written before.'}
              action={
                <Button type="button" variant="secondary" disabled={uploading} onClick={onAddCovers}>
                  {uploading ? <Loader2 className="animate-spin" /> : <Upload />}
                  {uploading ? 'Uploading…' : 'Choose PDFs'}
                </Button>
              }
            />
          </div>
        )}
      </div>

      <ConfirmAction
        open={removing != null}
        onOpenChange={(v) => !v && setRemoving(null)}
        title="Remove this cover letter?"
        description={removing ? `“${displayName(removing)}” won’t be used for new cover letters. Letters already written stay as they are.` : ''}
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          if (removing) await onRemoveCover(removing.id)
        }}
      />
    </div>
  )
}

function DocRow({
  title,
  meta,
  expanded,
  onToggle,
  actions,
  children,
}: {
  title: string
  meta: string
  expanded: boolean
  onToggle: () => void
  actions: ReactNode
  children: ReactNode
}) {
  return (
    <li>
      <div className="flex items-center gap-2 py-2 pr-2 pl-2 md:gap-3 md:pr-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex min-h-12 min-w-0 flex-1 items-center gap-3 rounded-md px-2 text-left transition-colors duration-(--dur-1) hover:bg-surface-muted focus-visible:outline-offset-0"
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-surface-muted text-muted-foreground">
            <FileText className="size-4" aria-hidden />
          </span>
          <span className="min-w-0 flex-1 py-1">
            <span className="block text-label break-words text-foreground">{title}</span>
            <span className="block text-caption text-muted-foreground">{meta}</span>
          </span>
          <span className="hidden shrink-0 items-center gap-1 text-caption text-muted-foreground sm:flex">
            {expanded ? 'Hide' : 'Preview'}
          </span>
          <ChevronDown
            className={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-2)', expanded && 'rotate-180')}
            aria-hidden
          />
        </button>
        <div className="flex shrink-0 items-center">{actions}</div>
      </div>
      {expanded ? <div className="border-t bg-surface-muted/50 p-3 md:p-4">{children}</div> : null}
    </li>
  )
}

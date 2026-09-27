import { useId, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { ChevronRight, FileText, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

type DisclosureProps = {
  title: ReactNode
  /** Muted one-liner shown next to the title, e.g. a count or current values. */
  summary?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}

/** Progressive disclosure for optional or advanced fields. */
export function Disclosure({ title, summary, defaultOpen = false, children, className }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="group relative -mx-2 flex min-h-11 w-[calc(100%+1rem)] items-center gap-2 rounded-md px-2 text-left transition-colors duration-(--dur-1) ease-out hover:bg-surface-muted md:min-h-10"
      >
        <ChevronRight
          className={cn(
            'size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-2) ease-out',
            open && 'rotate-90',
          )}
          aria-hidden
        />
        <span className="text-label text-foreground">{title}</span>
        {summary ? <span className="ml-auto min-w-0 truncate pl-2 text-caption text-muted-foreground">{summary}</span> : null}
      </button>
      {open ? (
        <div id={id} className="pt-4">
          {children}
        </div>
      ) : null}
    </div>
  )
}

type DropZoneProps = {
  onFiles: (files: File[]) => void
  multiple?: boolean
  disabled?: boolean
  title: ReactNode
  detail: ReactNode
  /** Show the file icon (a file is chosen) instead of the upload icon. */
  hasFile?: boolean
}

function pdfsOnly(list: FileList | null): File[] {
  const files = [...(list ?? [])]
  const pdfs = files.filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))
  if (files.length && pdfs.length < files.length) toast.error('Only PDF files can be added.')
  return pdfs
}

/** Click or drop PDFs. */
export function DropZone({ onFiles, multiple, disabled, title, detail, hasFile }: DropZoneProps) {
  const ref = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const Icon = hasFile ? FileText : Upload

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    if (disabled) return
    const files = pdfsOnly(e.dataTransfer.files)
    if (files.length) onFiles(multiple ? files : files.slice(0, 1))
  }

  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="application/pdf,.pdf"
        multiple={multiple}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const files = pdfsOnly(e.target.files)
          if (files.length) onFiles(files)
          e.target.value = ''
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => ref.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          'flex w-full flex-col items-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface px-6 py-9 text-center transition-colors duration-(--dur-1) ease-out hover:border-primary/60 hover:bg-accent/40 disabled:pointer-events-none disabled:opacity-60 md:py-10',
          over && 'border-primary bg-accent',
          hasFile && 'border-solid',
        )}
      >
        <span
          className={cn(
            'flex size-11 items-center justify-center rounded-full',
            hasFile ? 'bg-accent text-accent-foreground' : 'bg-surface-muted text-muted-foreground',
          )}
        >
          <Icon className="size-5" aria-hidden />
        </span>
        <span className="min-w-0 max-w-full">
          <span className="block truncate text-label text-foreground">{title}</span>
          <span className="mt-1 block text-caption text-muted-foreground">{detail}</span>
        </span>
      </button>
    </>
  )
}

/** Muted group for nested content inside a card (no border inside a border). */
export function MutedList({ children, className }: { children: ReactNode; className?: string }) {
  return <ul className={cn('divide-y divide-border rounded-lg bg-surface-muted', className)}>{children}</ul>
}

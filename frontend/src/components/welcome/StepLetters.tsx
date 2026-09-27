import { ArrowLeft, ArrowRight, Check, FileText, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropZone, MutedList } from './parts'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  letters: string[]
  uploading: boolean
  onUpload: (files: File[]) => void
  onBack: () => void
  onContinue: () => void
}

export function StepLetters({ letters, uploading, onUpload, onBack, onContinue }: Props) {
  return (
    <WelcomeStep
      title="Add cover letters you’ve written"
      description="Two or three real letters are plenty. The letters we write for you will then sound like you. This step is optional; you can add them later in Settings."
      back={
        <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={uploading}>
          <ArrowLeft /> Back
        </Button>
      }
      actions={
        letters.length ? (
          <Button type="button" size="sm" onClick={onContinue} disabled={uploading}>
            Continue <ArrowRight />
          </Button>
        ) : (
          <Button type="button" size="sm" variant="ghost" onClick={onContinue} disabled={uploading}>
            Skip for now
          </Button>
        )
      }
    >
      <DropZone
        multiple
        disabled={uploading}
        onFiles={onUpload}
        hasFile={false}
        title={uploading ? 'Uploading…' : letters.length ? 'Add more letters' : 'Choose cover letters'}
        detail="PDF files. Drop them here or browse. Only you can see them."
      />
      {letters.length || uploading ? (
        <MutedList className="mt-4">
          {letters.map((l) => (
            <li key={l} className="flex items-center gap-3 px-4 py-3">
              <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-body">{l}</span>
              <Check className="size-4 shrink-0 text-success" aria-label="Uploaded" />
            </li>
          ))}
          {uploading ? (
            <li className="flex items-center gap-3 px-4 py-3 text-body text-muted-foreground">
              <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden /> Uploading…
            </li>
          ) : null}
        </MutedList>
      ) : null}
    </WelcomeStep>
  )
}

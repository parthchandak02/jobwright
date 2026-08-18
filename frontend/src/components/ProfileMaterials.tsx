import { useEffect, useState } from 'react'
import { Trash2, Upload } from 'lucide-react'
import { ResumePreview } from '@/components/ResumePreview'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { CoverLetterExample } from '@/lib/api'

type ResumeSlot = {
  pdfUrl: string | null
  markdown: string
  replacing?: boolean
  onReplace: () => void
}

type Props = {
  resume: ResumeSlot
  examples: CoverLetterExample[]
  uploading?: boolean
  onAddCovers: () => void
  onRemoveCover: (id: string) => void
}

const RESUME_TAB = 'resume'

function coverTab(id: string): string {
  return `cover:${id}`
}

function displayName(example: CoverLetterExample): string {
  return example.filename.replace(/\.(pdf|txt)$/i, '').replaceAll('_', ' ')
}

export function ProfileMaterials({
  resume,
  examples,
  uploading,
  onAddCovers,
  onRemoveCover,
}: Props) {
  const [doc, setDoc] = useState(RESUME_TAB)

  useEffect(() => {
    if (doc === RESUME_TAB) return
    const id = doc.slice('cover:'.length)
    if (!examples.some((ex) => ex.id === id)) {
      setDoc(RESUME_TAB)
    }
  }, [doc, examples])

  return (
    <Tabs
      value={doc}
      onValueChange={setDoc}
      orientation="vertical"
      className="flex-col gap-3 md:flex-row md:items-start"
    >
      <div className="flex w-full shrink-0 flex-col gap-2 md:w-48">
        <TabsList className="flex h-auto max-h-40 w-full flex-col items-stretch justify-start gap-0.5 overflow-y-auto md:max-h-[min(90vh,1100px)]">
          <TabsTrigger
            value={RESUME_TAB}
            className="h-auto w-full flex-none justify-start py-1.5 text-left"
          >
            Resume
          </TabsTrigger>
          {examples.map((example) => (
            <TabsTrigger
              key={example.id}
              value={coverTab(example.id)}
              className="h-auto w-full flex-none justify-start py-1.5 text-left"
            >
              <span className="truncate">{displayName(example)}</span>
            </TabsTrigger>
          ))}
        </TabsList>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={uploading}
          onClick={onAddCovers}
        >
          <Upload />
          {uploading ? 'Uploading…' : 'Add cover PDFs'}
        </Button>
      </div>

      <div className="min-w-0 flex-1">
        <TabsContent value={RESUME_TAB}>
          <ResumePreview
            pdfUrl={resume.pdfUrl}
            markdown={resume.markdown}
            actions={
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={resume.replacing}
                onClick={resume.onReplace}
              >
                <Upload />
                {resume.replacing ? 'Uploading…' : resume.pdfUrl ? 'Replace PDF' : 'Add PDF'}
              </Button>
            }
          />
        </TabsContent>

        {examples.map((example) => (
          <TabsContent key={example.id} value={coverTab(example.id)}>
            <ResumePreview
              pdfUrl={
                example.kind !== 'txt'
                  ? `/api/settings/cover-letters/${encodeURIComponent(example.id)}/pdf?t=${example.mtime}`
                  : null
              }
              markdown={example.markdown}
              pdfTitle={`${example.filename} preview`}
              emptyPdf="No PDF on file."
              emptyMarkdown="No markdown yet. It appears after the PDF is converted on the server."
              actions={
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={uploading}
                  onClick={() => onRemoveCover(example.id)}
                >
                  <Trash2 />
                  Remove
                </Button>
              }
            />
          </TabsContent>
        ))}
      </div>
    </Tabs>
  )
}

import { FileText, Mail, MessageSquareReply } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { JobCard } from '@/lib/api'

type Props = {
  job: Pick<
    JobCard,
    'source' | 'has_resume' | 'has_cover' | 'first_response_at' | 'outcome'
  >
}

export function JobMetaBadges({ job }: Props) {
  return (
    <div className="flex flex-wrap gap-1">
      {job.source === 'manual' && <Badge variant="secondary">manual</Badge>}
      {job.has_resume && (
        <Badge variant="success">
          <FileText /> resume
        </Badge>
      )}
      {job.has_cover && (
        <Badge variant="info">
          <Mail /> cover
        </Badge>
      )}
      {job.first_response_at && (
        <Badge variant="warning">
          <MessageSquareReply /> reply
        </Badge>
      )}
      {job.outcome && <Badge variant="outline">{job.outcome}</Badge>}
    </div>
  )
}

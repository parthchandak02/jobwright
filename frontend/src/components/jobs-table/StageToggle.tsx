import { Check } from 'lucide-react'
import { Chip } from '@/components/Chip'
import { STAGE_LABELS, STAGE_TONE } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import type { FilterProps } from './types'

function StageToggle({ stage, selected, onToggle }: { stage: string; selected: boolean; onToggle: () => void }) {
  const Icon = NAV_ICONS[stage]
  return (
    <button type="button" aria-pressed={selected} onClick={onToggle} className="touch-target relative rounded-full">
      {selected ? (
        <Chip icon={Check} tone={STAGE_TONE[stage]}>
          {STAGE_LABELS[stage] || stage}
        </Chip>
      ) : (
        <Chip icon={Icon}>{STAGE_LABELS[stage] || stage}</Chip>
      )}
    </button>
  )
}

/** One toggle chip per stage; selected stages filter the list. */
export function StageToggles({ stages, filters, setFilters }: FilterProps & { stages: string[] }) {
  return (
    <>
      {stages.map((stage) => {
        const selected = filters.stages.includes(stage)
        return (
          <StageToggle
            key={stage}
            stage={stage}
            selected={selected}
            onToggle={() =>
              setFilters((f) => ({
                ...f,
                stages: selected ? f.stages.filter((s) => s !== stage) : [...f.stages, stage],
              }))
            }
          />
        )
      })}
    </>
  )
}

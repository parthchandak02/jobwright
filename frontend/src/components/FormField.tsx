import { Fragment, cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react'
import { FieldHint } from '@/components/FieldHint'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

type Props = {
  label: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
  /** Short help shown under the control (visible, not a tooltip). */
  hint?: ReactNode
  /** Longer explanation behind a "?" popover next to the label. */
  help?: ReactNode
  /** Adds a muted "(optional)" after the label. */
  optional?: boolean
  error?: ReactNode
  /** Right side of the label row, e.g. a status or a small link. */
  labelAction?: ReactNode
}

type ControlProps = { id?: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }

export function FormField({ label, htmlFor, children, className, hint, help, optional, error, labelAction }: Props) {
  const autoId = useId()
  const controlId = htmlFor ?? `${autoId}-control`
  const hintId = hint ? `${autoId}-hint` : undefined
  const errorId = error ? `${autoId}-error` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  let control = children
  if (isValidElement(children) && children.type !== Fragment) {
    const el = children as ReactElement<ControlProps>
    control = cloneElement(el, {
      id: el.props.id ?? (htmlFor ? undefined : controlId),
      'aria-describedby': [el.props['aria-describedby'], describedBy].filter(Boolean).join(' ') || undefined,
      ...(error ? { 'aria-invalid': true } : {}),
    })
  }

  return (
    <div data-slot="form-field" className={cn('flex flex-col', className)}>
      <div className="mb-2 flex min-h-5 items-center gap-1.5">
        <Label htmlFor={controlId}>
          {label}
          {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
        </Label>
        {help ? <FieldHint text={help} /> : null}
        {labelAction ? <div className="ml-auto flex items-center gap-2">{labelAction}</div> : null}
      </div>
      {control}
      {error ? (
        <p id={errorId} className="mt-1.5 text-caption text-destructive">
          {error}
        </p>
      ) : null}
      {hint ? (
        <p id={hintId} className="mt-1.5 text-caption text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

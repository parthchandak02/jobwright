import * as React from 'react'
import { controlBase } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type TextareaProps = React.ComponentProps<'textarea'> & {
  autoGrow?: boolean
}

const supportsFieldSizing =
  typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('field-sizing', 'content')

function Textarea({ className, autoGrow = true, rows = 3, style, onInput, ref, ...props }: TextareaProps) {
  const innerRef = React.useRef<HTMLTextAreaElement | null>(null)
  const needsJs = autoGrow && !supportsFieldSizing

  const resize = React.useCallback(() => {
    const el = innerRef.current
    if (!el || !needsJs) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight + 2}px`
  }, [needsJs])

  React.useLayoutEffect(resize, [resize, props.value])

  const setRef = React.useCallback(
    (el: HTMLTextAreaElement | null) => {
      innerRef.current = el
      if (typeof ref === 'function') ref(el)
      else if (ref) ref.current = el
    },
    [ref],
  )

  return (
    <textarea
      ref={setRef}
      data-slot="textarea"
      rows={rows}
      onInput={(e) => {
        resize()
        onInput?.(e)
      }}
      style={autoGrow ? { minHeight: `calc(${rows}lh + 1.25rem + 2px)`, ...style } : style}
      className={cn(
        controlBase,
        'block px-3 py-2.5 leading-relaxed',
        autoGrow ? 'field-sizing-content max-h-[60vh] resize-none overflow-y-auto' : 'min-h-20 resize-y',
        className,
      )}
      {...props}
    />
  )
}

export { Textarea, type TextareaProps }

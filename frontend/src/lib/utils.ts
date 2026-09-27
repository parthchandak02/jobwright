import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ['display', 'title', 'heading', 'subheading', 'body', 'label', 'caption', 'micro'],
      shadow: ['e1', 'e2'],
      radius: ['popover'],
      container: ['form', 'wide', 'welcome'],
      spacing: ['field', 'section', 'page-x', 'page-top'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

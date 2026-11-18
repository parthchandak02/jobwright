/** True when markdown has copyable content (not empty/whitespace). */
export function hasCopyableMarkdown(markdown: string | null | undefined): boolean {
  return (markdown ?? '').trim().length > 0
}

/**
 * Strip Markdown syntax so ATS paste fields get readable plain text.
 * Keeps line breaks and list bullets as plain characters; drops headings,
 * emphasis, and link/image wrappers.
 */
export function markdownToPlainText(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const out = lines.map((line) => {
    let s = line
    s = s.replace(/^(\s*)#{1,6}\s+/, '$1')
    s = s.replace(/^(\s*)>\s?/, '$1')

    let prefix = ''
    let body = s
    const ul = s.match(/^(\s*)([-*+])\s+(.*)$/)
    if (ul) {
      prefix = `${ul[1]}- `
      body = ul[3]
    } else {
      const ol = s.match(/^(\s*)(\d+\.)\s+(.*)$/)
      if (ol) {
        prefix = `${ol[1]}${ol[2]} `
        body = ol[3]
      }
    }

    body = body.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    body = body.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    body = body.replace(/`([^`]+)`/g, '$1')
    body = body.replace(/\*\*([^*]+)\*\*/g, '$1')
    body = body.replace(/__([^_]+)__/g, '$1')
    body = body.replace(/\*([^*]+)\*/g, '$1')
    body = body.replace(/_([^_]+)_/g, '$1')
    body = body.replace(/~~([^~]+)~~/g, '$1')
    return prefix + body
  })
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

/**
 * Plain text ready to copy from materials markdown, or null when Copy should
 * stay disabled (empty / whitespace-only source).
 */
export function materialsCopyPlainText(
  markdown: string | null | undefined,
): string | null {
  if (!hasCopyableMarkdown(markdown)) return null
  const plain = markdownToPlainText(markdown ?? '')
  return plain.trim().length > 0 ? plain : null
}

function copyViaExecCommand(text: string): boolean {
  if (typeof document === 'undefined') return false
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  ta.style.top = '0'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(ta)
  }
}

/** Write plain text to the clipboard. Returns whether the write succeeded. */
export async function writeClipboardText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through to execCommand (insecure origin / some mobile webviews).
  }
  try {
    return copyViaExecCommand(text)
  } catch {
    return false
  }
}

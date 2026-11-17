/** True when markdown has copyable content (not empty/whitespace). */
export function hasCopyableMarkdown(markdown: string | null | undefined): boolean {
  return (markdown ?? '').trim().length > 0
}

/** Write plain text to the clipboard. Returns whether the write succeeded. */
export async function writeClipboardText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

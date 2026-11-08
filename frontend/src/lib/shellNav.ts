/** Pure helpers for the shell links (desktop sidebar + phone tab bar). */

export type NavLinkShape = {
  path: string
  /** Query string that is part of the link, e.g. "?tab=claude". */
  search?: string
  /** Shown in the phone tab bar only when it fits (at most PHONE_TAB_MAX tabs). */
  phoneOptional?: boolean
}

export const PHONE_TAB_MAX = 5

const params = (search: string) => new URLSearchParams(search)

/** Does `search` carry every parameter of the link's own query? */
function hasQuery(linkSearch: string, search: string): boolean {
  const want = params(linkSearch)
  const have = params(search)
  for (const [k, v] of want) if (have.get(k) !== v) return false
  return true
}

/**
 * Is this link the current page? A link with its own query (Settings → Claude) wins over the plain
 * path (Settings), so only one of them is marked.
 */
export function isLinkActive<T extends NavLinkShape>(link: T, pathname: string, search: string, links: T[]): boolean {
  if (link.path === '/') return pathname === '/' || pathname.startsWith('/jobs/')
  if (!pathname.startsWith(link.path)) return false
  if (link.search) return hasQuery(link.search, search)
  return !links.some((other) => other !== link && other.path === link.path && other.search && hasQuery(other.search, search))
}

/** Phone tabs: drop optional links when the bar would hold more than PHONE_TAB_MAX tabs. */
export function phoneTabs<T extends NavLinkShape>(links: T[]): T[] {
  if (links.length <= PHONE_TAB_MAX) return links
  return links.filter((l) => !l.phoneOptional)
}

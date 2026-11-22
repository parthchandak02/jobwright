/** @vitest-environment jsdom */
import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { JOB_KEY_ATTR } from '@/lib/jobPanel'
import { JobSidePanel, type ListNav } from './JobSidePanel'

function mountBoard(ids: string[]) {
  const main = document.createElement('main')
  const section = document.createElement('section')
  for (const id of ids) {
    const card = document.createElement('div')
    card.setAttribute(JOB_KEY_ATTR, id)
    card.tabIndex = 0
    card.getClientRects = () => [new DOMRect(0, 0, 100, 40)] as unknown as DOMRectList
    card.scrollIntoView = () => {}
    section.appendChild(card)
  }
  main.appendChild(section)
  document.body.appendChild(main)
  return main
}

function renderPanel(jobKey: string, listNav: ListNav | null, onOpenJob = vi.fn()) {
  render(
    createElement(
      JobSidePanel,
      {
        jobKey,
        title: `Role ${jobKey}`,
        onClose: () => {},
        onOpenJob,
        listLabel: listNav ? "1 of 2 on today's list" : null,
        listNav,
        children: () => createElement('div', null, 'body'),
      },
    ),
  )
  return onOpenJob
}

beforeEach(() => {
  vi.useFakeTimers()
  if (!globalThis.CSS?.escape) {
    vi.stubGlobal('CSS', { escape: (s: string) => s })
  }
  if (!globalThis.DOMRect) {
    vi.stubGlobal(
      'DOMRect',
      class {
        constructor(
          public x = 0,
          public y = 0,
          public width = 0,
          public height = 0,
        ) {}
      },
    )
  }
})

afterEach(() => {
  cleanup()
  vi.runAllTimers()
  vi.useRealTimers()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('JobSidePanel list navigation', () => {
  it('at the end of a daily list, disables Next and does not fall back to the lane neighbor', () => {
    const main = mountBoard(['lane-prev', 'list-last', 'lane-next'])
    const onOpenJob = renderPanel('list-last', { prevId: 'list-prev', nextId: null })

    const nextBtn = screen.getByRole('button', { name: 'Next on the list' }) as HTMLButtonElement
    expect(nextBtn.disabled).toBe(true)
    fireEvent.click(nextBtn)
    fireEvent.keyDown(document.body, { key: 'j' })

    const openCard = main.querySelector(`[${JOB_KEY_ATTR}="list-last"]`) as HTMLElement
    fireEvent.keyDown(openCard, { key: 'ArrowDown' })
    expect(onOpenJob).not.toHaveBeenCalled()
  })

  it('at the start of a daily list, disables Previous and does not fall back to the lane neighbor', () => {
    const main = mountBoard(['lane-prev', 'list-first', 'lane-next'])
    const onOpenJob = renderPanel('list-first', { prevId: null, nextId: 'list-next' })

    const prevBtn = screen.getByRole('button', { name: 'Previous on the list' }) as HTMLButtonElement
    expect(prevBtn.disabled).toBe(true)
    fireEvent.click(prevBtn)
    fireEvent.keyDown(document.body, { key: 'k' })

    const openCard = main.querySelector(`[${JOB_KEY_ATTR}="list-first"]`) as HTMLElement
    fireEvent.keyDown(openCard, { key: 'ArrowUp' })
    expect(onOpenJob).not.toHaveBeenCalled()
  })

  it('uses list prev and next for both buttons and j / k shortcuts', () => {
    mountBoard(['lane-prev', 'list-mid', 'lane-next'])
    const onOpenJob = renderPanel('list-mid', { prevId: 'list-prev', nextId: 'list-next' })

    fireEvent.click(screen.getByRole('button', { name: 'Previous on the list' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next on the list' }))
    fireEvent.keyDown(document.body, { key: 'k' })
    fireEvent.keyDown(document.body, { key: 'j' })

    expect(onOpenJob.mock.calls).toEqual([['list-prev'], ['list-next'], ['list-prev'], ['list-next']])
  })

  it('off the list, keeps lane navigation for Previous and Next', () => {
    mountBoard(['lane-prev', 'job-open', 'lane-next'])
    const onOpenJob = renderPanel('job-open', null)

    fireEvent.click(screen.getByRole('button', { name: 'Previous job' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next job' }))
    fireEvent.keyDown(document.body, { key: 'k' })
    fireEvent.keyDown(document.body, { key: 'j' })

    expect(onOpenJob.mock.calls).toEqual([['lane-prev'], ['lane-next'], ['lane-prev'], ['lane-next']])
  })

  it('on a list job, ArrowDown/ArrowUp on another focused board card still steps in that lane', () => {
    const main = mountBoard(['lane-prev', 'list-mid', 'lane-next'])
    const onOpenJob = renderPanel('list-mid', { prevId: 'list-prev', nextId: 'list-next' })

    const otherCard = main.querySelector(`[${JOB_KEY_ATTR}="lane-prev"]`) as HTMLElement
    fireEvent.keyDown(otherCard, { key: 'ArrowDown' })
    expect(onOpenJob.mock.calls).toEqual([['list-mid']])
  })
})

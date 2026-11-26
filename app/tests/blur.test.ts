import { describe, expect, it } from 'vitest'
import { SHOW_GRACE_MS, pointInside, shouldHideOnBlur, type BlurContext } from '../src/main/blur'
import { parseConfirm } from '../src/main/files'

const base: BlurContext = {
  enabled: true, visible: true, dialogOpen: false, devToolsOpen: false, msSinceShow: 5_000,
  cursor: { x: 200, y: 300 }, bounds: { x: 1140, y: 0, width: 460, height: 1000 },
}

describe('hide on click outside', () => {
  it('hides when focus is lost with the pointer outside the panel', () => {
    expect(shouldHideOnBlur(base)).toBe(true)
  })

  it('stays for focus changes that belong to the panel (select list, date picker: pointer inside)', () => {
    expect(shouldHideOnBlur({ ...base, cursor: { x: 1300, y: 86 } })).toBe(false)
  })

  it('stays when pinned, during a dialog, with devtools, or right after opening', () => {
    expect(shouldHideOnBlur({ ...base, enabled: false })).toBe(false)
    expect(shouldHideOnBlur({ ...base, dialogOpen: true })).toBe(false)
    expect(shouldHideOnBlur({ ...base, devToolsOpen: true })).toBe(false)
    expect(shouldHideOnBlur({ ...base, msSinceShow: SHOW_GRACE_MS - 1 })).toBe(false)
    expect(shouldHideOnBlur({ ...base, visible: false })).toBe(false)
  })

  it('bounds are half-open (the pixel right of the panel is outside)', () => {
    const b = base.bounds
    expect(pointInside({ x: b.x, y: 0 }, b)).toBe(true)
    expect(pointInside({ x: b.x + b.width, y: 0 }, b)).toBe(false)
    expect(pointInside({ x: b.x - 1, y: 10 }, b)).toBe(false)
  })
})

describe('native confirmation requests', () => {
  it('accepts bounded strings only', () => {
    expect(parseConfirm({ message: 'Supprimer ?', detail: 'x', confirmLabel: 'Supprimer' })).toEqual({ message: 'Supprimer ?', detail: 'x', confirmLabel: 'Supprimer' })
    expect(parseConfirm({ message: 'ok' })).toEqual({ message: 'ok', detail: '', confirmLabel: 'OK' })
    expect(parseConfirm({ message: '' })).toBeNull()
    expect(parseConfirm({ message: 'x'.repeat(301) })).toBeNull()
    expect(parseConfirm(null)).toBeNull()
    expect(parseConfirm({ message: 'm', confirmLabel: 'x'.repeat(41) })?.confirmLabel).toBe('OK')
  })
})

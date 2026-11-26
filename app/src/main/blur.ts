/**
 * Should the side panel hide when it loses focus? (click outside, like aska)
 *
 * It must NOT hide for focus changes that belong to the panel itself: a native <select> list or a date
 * picker opened from the panel, a save/confirm dialog, devtools, or the spurious blur some window
 * managers send right after showing a window. The robust signal for "clicked elsewhere" is: the
 * pointer is outside the panel when focus is lost.
 */

export interface BlurContext {
  enabled: boolean // the "hide when I click elsewhere" setting (pin button off)
  visible: boolean
  dialogOpen: boolean
  devToolsOpen: boolean
  msSinceShow: number
  cursor: { x: number; y: number }
  bounds: { x: number; y: number; width: number; height: number }
}

export const SHOW_GRACE_MS = 300

export function pointInside(p: { x: number; y: number }, b: BlurContext['bounds']): boolean {
  return p.x >= b.x && p.x < b.x + b.width && p.y >= b.y && p.y < b.y + b.height
}

export function shouldHideOnBlur(c: BlurContext): boolean {
  if (!c.enabled || !c.visible || c.dialogOpen || c.devToolsOpen) return false
  if (c.msSinceShow < SHOW_GRACE_MS) return false
  return !pointInside(c.cursor, c.bounds)
}

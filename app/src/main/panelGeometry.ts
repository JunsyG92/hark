/** Where the side panel goes: right edge of the screen the cursor is on, full work-area height. */

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export const PANEL_WIDTH = 460 // includes the transparent margin used for the shadow

export function panelBounds(workArea: Rect, width = PANEL_WIDTH): Rect {
  const w = Math.min(width, workArea.width)
  return { x: workArea.x + workArea.width - w, y: workArea.y, width: w, height: workArea.height }
}

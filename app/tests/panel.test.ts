import { expect, it } from 'vitest'
import { PANEL_WIDTH, panelBounds } from '../src/main/panelGeometry'

it('docks the panel on the right edge, full height, on any screen', () => {
  expect(panelBounds({ x: 0, y: 32, width: 1920, height: 1048 })).toEqual({ x: 1920 - PANEL_WIDTH, y: 32, width: PANEL_WIDTH, height: 1048 })
  expect(panelBounds({ x: 1920, y: 0, width: 1280, height: 1024 })).toEqual({ x: 3200 - PANEL_WIDTH, y: 0, width: PANEL_WIDTH, height: 1024 })
  expect(panelBounds({ x: 0, y: 0, width: 400, height: 700 }).width).toBe(400) // tiny screen: never wider than it
})

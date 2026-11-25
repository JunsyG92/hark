import type { HarkBridge } from '../../preload'

declare global {
  interface Window {
    hark: HarkBridge
  }
}

export {}

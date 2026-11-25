import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
// @ts-expect-error - plain ESM script without types
import { outFile, render } from '../scripts/gen-contract-types.mjs'

it('generated contract types are in sync with /contracts (run `pnpm contracts:types`)', async () => {
  expect(readFileSync(outFile as string, 'utf8')).toBe(await (render as () => Promise<string>)())
})

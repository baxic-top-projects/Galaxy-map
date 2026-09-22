#!/usr/bin/env node
// Runs the Vitest suite once. CI (and other CRA-era callers) invoke
// `npm test -- --watchAll=false`; Vitest has no `--watchAll` option and exits
// with "Unknown option", so strip that flag before forwarding the rest.
import { spawn } from 'node:child_process'

const args = process.argv.slice(2)
const forwarded = []

for (let i = 0; i < args.length; i += 1) {
  const arg = args[i]

  if (/^--(no-)?watchAll=/.test(arg)) continue

  if (/^--(no-)?watchAll$/.test(arg)) {
    // Tolerate the space-separated form (`--watchAll false`) too.
    if (/^(true|false)$/.test(args[i + 1] ?? '')) i += 1
    continue
  }

  forwarded.push(arg)
}

const child = spawn('vitest', ['run', ...forwarded], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
})

child.on('error', (error) => {
  console.error(error)
  process.exit(1)
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
    return
  }
  process.exit(code ?? 1)
})

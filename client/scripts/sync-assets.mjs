#!/usr/bin/env node
/**
 * Sync map textures and type models from EfolsMiradinsPact into client/public.
 * Large GLBs (>40MB) are skipped; preview PNGs are always copied for textured fallbacks.
 */
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..')
const CANON = process.env.EFOLS_ROOT || 'D:\\GitHub\\EfolsMiradinsPact'
const PUBLIC = join(ROOT, 'client', 'public')
const MAX_GLB_BYTES = 40 * 1024 * 1024

function ensureDir(dir) {
  mkdirSync(dir, { recursive: true })
}

function copyIfExists(src, dest) {
  if (!existsSync(src)) return false
  ensureDir(join(dest, '..'))
  copyFileSync(src, dest)
  return true
}

function syncFolder(srcDir, destDir, { glb = false } = {}) {
  ensureDir(destDir)
  if (!existsSync(srcDir)) {
    console.warn(`Missing source folder: ${srcDir}`)
    return { copied: 0, skipped: 0 }
  }
  let copied = 0
  let skipped = 0
  for (const name of readdirSync(srcDir)) {
    const src = join(srcDir, name)
    if (!statSync(src).isFile()) continue
    const lower = name.toLowerCase()
    if (glb) {
      if (!lower.endsWith('.glb')) continue
      if (statSync(src).size > MAX_GLB_BYTES) {
        console.warn(`Skip oversized GLB: ${name}`)
        skipped += 1
        continue
      }
    } else if (!lower.endsWith('.png') || lower.includes('_preview')) {
      // keep type art PNGs; preview files go through models folders
      if (!(lower.endsWith('_preview.png') && srcDir.includes('models'))) continue
      if (!lower.endsWith('.png')) continue
    }
    copyFileSync(src, join(destDir, name))
    copied += 1
  }
  return { copied, skipped }
}

function syncPreviews(srcDir, destDir) {
  ensureDir(destDir)
  if (!existsSync(srcDir)) return 0
  let copied = 0
  for (const name of readdirSync(srcDir)) {
    if (!name.toLowerCase().endsWith('_preview.png')) continue
    copyFileSync(join(srcDir, name), join(destDir, name))
    copied += 1
  }
  return copied
}

const report = {
  politicalMap: copyIfExists(
    join(CANON, 'assets', 'galaxy_political_map.png'),
    join(PUBLIC, 'textures', 'galaxy_political_map.png'),
  ),
  territoryPlate: copyIfExists(
    join(CANON, 'assets', 'galaxy_territory_plate.png'),
    join(PUBLIC, 'textures', 'galaxy_territory_plate.png'),
  ),
  basePlate: copyIfExists(
    join(CANON, 'assets', 'galaxy_base_plate.png'),
    join(PUBLIC, 'textures', 'galaxy_base_plate.png'),
  ),
  starGlb: syncFolder(join(CANON, 'assets', 'models', 'stars'), join(PUBLIC, 'models', 'stars'), {
    glb: true,
  }),
  planetGlb: syncFolder(
    join(CANON, 'assets', 'models', 'planets'),
    join(PUBLIC, 'models', 'planets'),
    { glb: true },
  ),
  featureGlb: syncFolder(
    join(CANON, 'assets', 'models', 'features'),
    join(PUBLIC, 'models', 'features'),
    { glb: true },
  ),
  starPreview: syncPreviews(
    join(CANON, 'assets', 'models', 'stars'),
    join(PUBLIC, 'models', 'stars'),
  ),
  planetPreview: syncPreviews(
    join(CANON, 'assets', 'models', 'planets'),
    join(PUBLIC, 'models', 'planets'),
  ),
  featurePreview: syncPreviews(
    join(CANON, 'assets', 'models', 'features'),
    join(PUBLIC, 'models', 'features'),
  ),
  starTypes: syncFolder(join(CANON, 'assets', 'star_types'), join(PUBLIC, 'textures', 'star_types')),
  planetTypes: syncFolder(
    join(CANON, 'assets', 'planet_types'),
    join(PUBLIC, 'textures', 'planet_types'),
  ),
  systemFeatures: syncFolder(
    join(CANON, 'assets', 'system_features'),
    join(PUBLIC, 'textures', 'system_features'),
  ),
}

writeFileSync(join(PUBLIC, 'models', 'manifest.json'), JSON.stringify(report, null, 2))
console.log(JSON.stringify(report, null, 2))
console.log('Asset sync complete.')

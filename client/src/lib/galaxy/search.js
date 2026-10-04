/**
 * Galaxy search — match visible names and the compact English token.
 *
 * Rules:
 * - Always search nameEn + nameRu (both languages).
 * - Prefer the active locale name in ranking.
 * - Token is the compact English name without spaces
 *   (CorvuthAltair ↔ "Corvuth Altair") and is always searchable.
 * - Deduplicate by id+kind+token, keep the best score.
 *
 * @param {Array<{ id?: string, nameEn: string, nameRu: string, token: string, kind: string, stem: string|null }>} entries
 * @param {string} query
 * @param {{ locale?: 'ru'|'en', limit?: number, stem?: string|null }} [options]
 */
export function filterSearch(entries, query, options = {}) {
  const locale = options.locale || 'ru'
  const limit = options.limit ?? 20
  const stem = options.stem ?? null
  const needle = normalize(query)
  if (!needle) return []

  /** @type {Map<string, { entry: any, score: number, label: string }>} */
  const bestByKey = new Map()

  for (const entry of entries) {
    if (stem && entry.stem !== stem) continue

    const nameEn = normalize(entry.nameEn)
    const nameRu = normalize(entry.nameRu)
    const token = normalize(entry.token)

    const primary = locale === 'en' ? nameEn : nameRu
    const secondary = locale === 'en' ? nameRu : nameEn

    /** @type {Array<{ text: string, tier: number }>} */
    const fields = []
    if (primary) fields.push({ text: primary, tier: 0 })
    if (token && token !== primary) fields.push({ text: token, tier: 1 })
    if (secondary && secondary !== primary && secondary !== token) {
      fields.push({ text: secondary, tier: 3 })
    }

    let score = -1
    let matchedLabel = primary || secondary || token
    for (const { text, tier } of fields) {
      const hit = fieldScore(text, needle)
      if (hit < 0) continue
      const ranked = hit + tier
      if (score < 0 || ranked < score) {
        score = ranked
        matchedLabel = text
      }
    }
    if (score < 0) continue

    const key = `${entry.id || ''}::${entry.kind || ''}::${entry.token || ''}`
    const prev = bestByKey.get(key)
    if (!prev || score < prev.score) {
      bestByKey.set(key, { entry, score, label: matchedLabel })
    }
  }

  return Array.from(bestByKey.values())
    .sort(
      (a, b) =>
        a.score - b.score ||
        a.label.localeCompare(b.label, locale === 'ru' ? 'ru' : 'en') ||
        (a.entry.token || '').localeCompare(b.entry.token || ''),
    )
    .slice(0, limit)
    .map((item) => item.entry)
}

function normalize(value) {
  return String(value || '')
    .trim()
    .toLocaleLowerCase('und')
}

/** 0 exact, 1 prefix, 2 substring, -1 none */
function fieldScore(field, needle) {
  if (!field) return -1
  if (field === needle) return 0
  if (field.startsWith(needle)) return 1
  if (field.includes(needle)) return 2
  return -1
}

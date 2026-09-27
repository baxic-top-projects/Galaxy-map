/**
 * Filter search entries by query string.
 * @param {Array<{ nameEn: string, nameRu: string, token: string, kind: string, stem: string|null }>} entries
 * @param {string} query
 * @param {{ locale?: 'ru'|'en', limit?: number, stem?: string|null }} [options]
 */
export function filterSearch(entries, query, options = {}) {
  const locale = options.locale || 'ru'
  const limit = options.limit ?? 20
  const stem = options.stem ?? null
  const needle = query.trim().toLowerCase()
  if (!needle) return []

  const scored = []
  for (const entry of entries) {
    if (stem && entry.stem !== stem) continue
    const name = (locale === 'en' ? entry.nameEn : entry.nameRu).toLowerCase()
    const token = entry.token.toLowerCase()
    let score = -1
    if (token === needle || name === needle) score = 0
    else if (token.startsWith(needle) || name.startsWith(needle)) score = 1
    else if (token.includes(needle) || name.includes(needle)) score = 2
    if (score >= 0) scored.push({ entry, score })
  }

  scored.sort((a, b) => a.score - b.score || a.entry.token.localeCompare(b.entry.token))
  return scored.slice(0, limit).map((item) => item.entry)
}

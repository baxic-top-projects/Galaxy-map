const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Persist a manual polity owner for one system.
 * @param {string} systemId
 * @param {string} stem
 * @param {string} [baseUrl]
 * @returns {Promise<{ id: string, stem: string, canonicalStem?: string }>}
 */
export async function updateSystemOwner(systemId, stem, baseUrl = DEFAULT_API_BASE) {
  if (!systemId) throw new Error('System id is required')
  if (!stem) throw new Error('Polity stem is required')
  const url = `${String(baseUrl).replace(/\/$/, '')}/api/v1/systems/${encodeURIComponent(systemId)}/owner`
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stem }),
  })
  if (!response.ok) {
    let detail = `Failed to update system owner: ${response.status}`
    try {
      const payload = await response.json()
      if (payload?.detail) detail = String(payload.detail)
    } catch {
      // Keep the status-based message when the body is empty.
    }
    throw new Error(detail)
  }
  return response.json()
}

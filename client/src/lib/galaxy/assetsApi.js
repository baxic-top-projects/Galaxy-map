const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Load S3/CDN model manifest from api-gateway.
 * Failures are non-fatal: the client keeps local /models fallbacks.
 * @param {string} [baseUrl]
 * @param {{ timeoutMs?: number }} [options]
 */
export async function fetchAssetManifest(baseUrl = DEFAULT_API_BASE, { timeoutMs = 5000 } = {}) {
  const url = `${String(baseUrl).replace(/\/$/, '')}/api/v1/assets/manifest`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) {
      throw new Error(`Failed to load asset manifest: ${response.status}`)
    }
    return response.json()
  } finally {
    clearTimeout(timeout)
  }
}

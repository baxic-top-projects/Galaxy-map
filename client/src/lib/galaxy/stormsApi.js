/**
 * @typedef {{
 *   systemId: string,
 *   intensity: number,
 *   stage: 'forming' | 'active' | 'dissipating',
 *   type: 'electric' | 'gravity' | 'particle' | 'shroud',
 *   stormId: string,
 *   color: string
 * }} SystemStormState
 *
 * @typedef {{
 *   tick: number,
 *   generatedAt: string,
 *   storms: object[],
 *   systems: SystemStormState[]
 * }} StormSnapshot
 */

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Normalize a storm snapshot into lookup maps used by the map UI.
 * bySystemId is a plain object (not Map) so Svelte $state proxies stay reliable.
 * @param {StormSnapshot|null|undefined} snapshot
 */
export function normalizeStormSnapshot(snapshot) {
  const systems = Array.isArray(snapshot?.systems) ? snapshot.systems : []
  /** @type {Record<string, SystemStormState>} */
  const bySystemId = {}
  for (const entry of systems) {
    if (!entry?.systemId) continue
    bySystemId[entry.systemId] = {
      systemId: entry.systemId,
      intensity: Number(entry.intensity) || 0,
      stage: entry.stage || 'active',
      type: entry.type || 'electric',
      stormId: entry.stormId || '',
      color: entry.color || '#6ec8ff',
    }
  }
  return {
    tick: Number(snapshot?.tick) || 0,
    generatedAt: snapshot?.generatedAt || '',
    storms: Array.isArray(snapshot?.storms) ? snapshot.storms : [],
    systems,
    bySystemId,
  }
}

/**
 * @param {ReturnType<typeof normalizeStormSnapshot>|null|undefined} snapshot
 * @param {string|null|undefined} systemId
 */
export function stormForSystem(snapshot, systemId) {
  if (!snapshot || !systemId) return null
  return snapshot.bySystemId?.[systemId] || null
}

export function stormWebSocketUrl(baseUrl) {
  // VITE_WS_URL only applies when no base URL is given; an explicit base URL wins.
  if (baseUrl === undefined) {
    const configured = import.meta.env.VITE_WS_URL
    if (configured) return `${String(configured).replace(/\/$/, '')}/api/v1/storms/ws`
    baseUrl = DEFAULT_API_BASE
  }

  if (!baseUrl) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/v1/storms/ws`
  }

  try {
    const url = new URL(baseUrl, window.location.origin)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `${url.pathname.replace(/\/$/, '')}/api/v1/storms/ws`
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/v1/storms/ws`
  }
}

/**
 * Subscribe to live storm snapshots over WebSocket.
 * @param {{
 *   baseUrl?: string,
 *   onSnapshot?: (snapshot: ReturnType<typeof normalizeStormSnapshot>) => void,
 *   onStatus?: (status: 'connecting' | 'open' | 'closed' | 'error') => void,
 * }} [options]
 */
export function connectStormSocket(options = {}) {
  const { baseUrl, onSnapshot, onStatus } = options
  let socket = null
  let closedByUser = false
  let reconnectTimer = 0
  let attempt = 0

  function clearReconnect() {
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = 0
    }
  }

  function scheduleReconnect() {
    if (closedByUser) return
    clearReconnect()
    const delay = Math.min(10000, 1000 * 2 ** Math.min(attempt, 3))
    attempt += 1
    reconnectTimer = window.setTimeout(connect, delay)
  }

  function connect() {
    clearReconnect()
    onStatus?.('connecting')
    const url = stormWebSocketUrl(baseUrl)
    socket = new WebSocket(url)

    socket.addEventListener('open', () => {
      attempt = 0
      onStatus?.('open')
    })

    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data)
        onSnapshot?.(normalizeStormSnapshot(payload))
      } catch {
        onStatus?.('error')
      }
    })

    socket.addEventListener('error', () => {
      onStatus?.('error')
    })

    socket.addEventListener('close', () => {
      onStatus?.('closed')
      socket = null
      scheduleReconnect()
    })
  }

  connect()

  return {
    close() {
      closedByUser = true
      clearReconnect()
      socket?.close()
      socket = null
    },
  }
}

/**
 * @param {string} [baseUrl]
 * @returns {Promise<ReturnType<typeof normalizeStormSnapshot>|null>}
 */
export async function fetchStormSnapshot(baseUrl = DEFAULT_API_BASE) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/v1/storms`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load storms: ${response.status}`)
  }
  return normalizeStormSnapshot(await response.json())
}

/**
 * @param {string} systemId
 * @param {string} [baseUrl]
 */
export async function fetchSystemStorm(systemId, baseUrl = DEFAULT_API_BASE) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/v1/storms/systems/${encodeURIComponent(systemId)}`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load system storm: ${response.status}`)
  }
  return response.json()
}

export function stormStageLabel(stage, locale = 'ru') {
  const map = {
    forming: { en: 'Forming', ru: 'Зарождение' },
    active: { en: 'Active', ru: 'Активна' },
    dissipating: { en: 'Dissipating', ru: 'Затухание' },
  }
  return map[stage]?.[locale] || stage
}

export function stormTypeLabel(type, locale = 'ru') {
  const map = {
    electric: { en: 'Electric storm', ru: 'Электрическая буря' },
    gravity: { en: 'Gravity storm', ru: 'Гравитационная буря' },
    particle: { en: 'Particle storm', ru: 'Частичная буря' },
    shroud: { en: 'Shroud storm', ru: 'Буря Покрова' },
  }
  return map[type]?.[locale] || type
}

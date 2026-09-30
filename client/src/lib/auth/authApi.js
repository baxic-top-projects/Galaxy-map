const API_BASE = String(import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')
const ACCESS_KEY = 'galaxy.accessToken'

let accessToken = sessionStorage.getItem(ACCESS_KEY) || ''

export function getAccessToken() {
  return accessToken
}

function setAccessToken(token) {
  accessToken = token || ''
  if (accessToken) sessionStorage.setItem(ACCESS_KEY, accessToken)
  else sessionStorage.removeItem(ACCESS_KEY)
}

async function request(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {})
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let response = await fetch(`${API_BASE}/api/v1/auth${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })
  if (response.status === 401 && retry && path !== '/refresh' && path !== '/login') {
    const refreshed = await refreshSession(false)
    if (refreshed) return request(path, options, false)
  }
  if (!response.ok) {
    let message = `Auth request failed: ${response.status}`
    try {
      const payload = await response.json()
      message = payload?.detail || payload?.message || message
    } catch {
      // Keep status message.
    }
    throw new Error(String(message))
  }
  if (response.status === 204) return null
  return response.json()
}

function acceptSession(payload) {
  setAccessToken(payload?.access_token || payload?.accessToken || '')
  return payload?.user || payload
}

export async function bootstrapSession() {
  if (accessToken) {
    try {
      return await request('/me')
    } catch {
      setAccessToken('')
    }
  }
  return refreshSession(false)
}

export async function refreshSession(throwOnError = true) {
  try {
    const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!response.ok) {
      setAccessToken('')
      if (throwOnError) throw new Error('Session expired')
      return null
    }
    return acceptSession(await response.json())
  } catch (error) {
    setAccessToken('')
    if (throwOnError) throw error
    return null
  }
}

export async function login(email, password) {
  return acceptSession(
    await request(
      '/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      false,
    ),
  )
}

export async function registerAccount(payload) {
  return request('/register', { method: 'POST', body: JSON.stringify(payload) }, false)
}

export async function logout() {
  try {
    await request('/logout', { method: 'POST' }, false)
  } finally {
    setAccessToken('')
  }
}

export function googleLoginUrl() {
  const returnTo = `${window.location.origin}/auth/callback`
  return `${API_BASE}/api/v1/auth/google/start?redirect_uri=${encodeURIComponent(returnTo)}`
}

export async function exchangeGoogleCode(code) {
  return acceptSession(
    await request(
      '/exchange-code',
      { method: 'POST', body: JSON.stringify({ code }) },
      false,
    ),
  )
}

export async function verifyEmail(token) {
  return request('/verify-email', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export async function resendVerification(email) {
  return request('/resend-verification', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export async function forgotPassword(email) {
  return request('/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export async function resetPassword(token, password) {
  return request('/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
  })
}

export async function updateProfile(payload) {
  return request('/profile', { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function uploadAvatar(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/profile/avatar', { method: 'POST', body: form })
}

export async function deleteAvatar() {
  return request('/profile/avatar', { method: 'DELETE' })
}

export async function promoteAdmin(email) {
  return request('/admin/promote', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

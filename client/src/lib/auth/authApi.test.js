import { beforeEach, describe, expect, test, vi } from 'vitest'

describe('logout pending retry', () => {
  beforeEach(() => {
    vi.resetModules()
    sessionStorage.clear()
    localStorage.clear()
  })

  test('marks pendingLogout when server logout fails, then flushes on retry', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: 'Logged out' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { logout, flushPendingLogout } = await import('./authApi.js')
    sessionStorage.setItem('galaxy.accessToken', 'access')

    await logout()
    expect(sessionStorage.getItem('galaxy.accessToken')).toBeNull()
    expect(localStorage.getItem('galaxy.pendingLogout')).toBe('1')

    await expect(flushPendingLogout()).resolves.toBe(true)
    expect(localStorage.getItem('galaxy.pendingLogout')).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  test('bootstrap does not refresh while pending logout remains', async () => {
    localStorage.setItem('galaxy.pendingLogout', '1')
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)

    const { bootstrapSession } = await import('./authApi.js')
    await expect(bootstrapSession()).resolves.toBeNull()
    // Only the pending logout attempt — no /refresh resurrection.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/logout')
  })
})

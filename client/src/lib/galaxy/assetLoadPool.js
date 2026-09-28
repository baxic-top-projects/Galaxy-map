/**
 * Bounded concurrency helpers for S3 / CDN asset loads.
 */

/**
 * @template T, R
 * @param {T[]} items
 * @param {number} limit
 * @param {(item: T, index: number) => Promise<R>} mapper
 * @returns {Promise<R[]>}
 */
export async function mapPool(items, limit, mapper) {
  const list = Array.isArray(items) ? items : []
  if (!list.length) return []
  const concurrency = Math.max(1, Math.min(limit, list.length))
  const results = new Array(list.length)
  let cursor = 0

  async function worker() {
    while (cursor < list.length) {
      const index = cursor
      cursor += 1
      results[index] = await mapper(list[index], index)
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()))
  return results
}

/**
 * Shared slot gate so GLB + texture requests do not stampede the browser / S3.
 * @param {number} [concurrency]
 */
export function createAssetLoadGate(concurrency = 6) {
  let active = 0
  /** @type {Array<() => void>} */
  const waiters = []

  function pump() {
    while (active < concurrency && waiters.length) {
      active += 1
      const releaseWaiter = waiters.shift()
      releaseWaiter?.()
    }
  }

  function acquire() {
    return new Promise((resolve) => {
      waiters.push(resolve)
      pump()
    })
  }

  function release() {
    active = Math.max(0, active - 1)
    pump()
  }

  /**
   * @template T
   * @param {() => Promise<T>} task
   * @returns {Promise<T>}
   */
  async function run(task) {
    await acquire()
    try {
      return await task()
    } finally {
      release()
    }
  }

  return { run, concurrency }
}

export const assetLoadGate = createAssetLoadGate(6)

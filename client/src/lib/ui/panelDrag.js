const STORAGE_PREFIX = 'galaxy-map:panel-pos:'

export function loadPanelPos(key) {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key)
    if (!raw) return { x: 0, y: 0 }
    const parsed = JSON.parse(raw)
    return {
      x: Number(parsed?.x) || 0,
      y: Number(parsed?.y) || 0,
    }
  } catch {
    return { x: 0, y: 0 }
  }
}

export function savePanelPos(key, pos) {
  try {
    localStorage.setItem(
      STORAGE_PREFIX + key,
      JSON.stringify({ x: pos.x || 0, y: pos.y || 0 }),
    )
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Pointer/touch drag for floating panels.
 * Uses window-level move/up listeners so iOS/Android keep tracking
 * even when the finger leaves the handle.
 *
 * @param {() => {x:number,y:number}} getPos
 * @param {(pos:{x:number,y:number}) => void} setPos
 * @param {string} storageKey
 * @param {{ onActive?: (active: boolean) => void }} [options]
 */
export function createPanelDrag(getPos, setPos, storageKey, options = {}) {
  let dragging = false
  let pointerId = null
  let handleEl = null
  let startX = 0
  let startY = 0
  let originX = 0
  let originY = 0
  let moved = false

  function cleanup() {
    const id = pointerId
    const handle = handleEl
    dragging = false
    pointerId = null
    handleEl = null
    options.onActive?.(false)
    window.removeEventListener('pointermove', onWindowMove)
    window.removeEventListener('pointerup', onWindowUp)
    window.removeEventListener('pointercancel', onWindowUp)
    try {
      if (handle && id != null) handle.releasePointerCapture?.(id)
    } catch {
      /* already released */
    }
  }

  function onWindowMove(event) {
    if (!dragging) return
    if (pointerId != null && event.pointerId !== pointerId) return
    const dx = event.clientX - startX
    const dy = event.clientY - startY
    if (!moved) {
      if (Math.hypot(dx, dy) < 8) return
      // Prefer native scrolling when the gesture is mostly vertical inside an
      // overflow card (system dossier on mobile).
      if (
        Math.abs(dy) > Math.abs(dx) * 1.15 &&
        handleEl instanceof Element &&
        handleEl.scrollHeight > handleEl.clientHeight + 1
      ) {
        cleanup()
        return
      }
      moved = true
    }
    if (event.cancelable) event.preventDefault()
    setPos({ x: originX + dx, y: originY + dy })
  }

  function onWindowUp(event) {
    if (!dragging) return
    if (pointerId != null && event.pointerId !== pointerId) return
    if (moved) savePanelPos(storageKey, getPos())
    cleanup()
  }

  function onPointerDown(event) {
    if (event.button != null && event.button !== 0) return
    if (event.target instanceof Element) {
      if (event.target.closest('button, a, input, select, textarea, label')) return
    }
    if (dragging) cleanup()

    dragging = true
    moved = false
    pointerId = event.pointerId
    handleEl = event.currentTarget
    startX = event.clientX
    startY = event.clientY
    const pos = getPos()
    originX = pos.x
    originY = pos.y
    options.onActive?.(true)

    window.addEventListener('pointermove', onWindowMove, { passive: false })
    window.addEventListener('pointerup', onWindowUp)
    window.addEventListener('pointercancel', onWindowUp)

    try {
      event.currentTarget.setPointerCapture?.(event.pointerId)
    } catch {
      /* some WebViews reject capture; window listeners still work */
    }
    if (event.cancelable) event.preventDefault()
  }

  return { onPointerDown }
}

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
 * Pointer drag for floating panels. Ignores clicks on interactive controls.
 * @param {() => {x:number,y:number}} getPos
 * @param {(pos:{x:number,y:number}) => void} setPos
 * @param {string} storageKey
 */
export function createPanelDrag(getPos, setPos, storageKey) {
  let dragging = false
  let startX = 0
  let startY = 0
  let originX = 0
  let originY = 0
  let moved = false

  function onPointerDown(event) {
    if (event.button != null && event.button !== 0) return
    if (event.target.closest('button, a, input, select, textarea, label')) return
    dragging = true
    moved = false
    startX = event.clientX
    startY = event.clientY
    const pos = getPos()
    originX = pos.x
    originY = pos.y
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  function onPointerMove(event) {
    if (!dragging) return
    const dx = event.clientX - startX
    const dy = event.clientY - startY
    if (!moved && Math.hypot(dx, dy) < 4) return
    moved = true
    setPos({ x: originX + dx, y: originY + dy })
  }

  function onPointerUp(event) {
    if (!dragging) return
    dragging = false
    try {
      event.currentTarget.releasePointerCapture?.(event.pointerId)
    } catch {
      /* already released */
    }
    if (moved) savePanelPos(storageKey, getPos())
  }

  return { onPointerDown, onPointerMove, onPointerUp }
}

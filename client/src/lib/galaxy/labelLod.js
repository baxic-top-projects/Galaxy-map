/**
 * Choose which systems should show labels for the current camera zoom.
 * @param {Array<{ id: string, capital?: boolean, worldCount?: number, x: number, y: number, z: number }>} systems
 * @param {{ zoom: number, selectedId?: string|null, hoveredId?: string|null, maxLabels?: number }} options
 */
export function pickLabels(systems, options) {
  const {
    zoom,
    selectedId = null,
    hoveredId = null,
    maxLabels = 48,
  } = options

  const chosen = []
  const seen = new Set()

  const push = (system, priority) => {
    // Junctions are anonymous graph nodes, never map labels (even selected).
    if (!system || system.kind === 'junction' || seen.has(system.id)) return
    seen.add(system.id)
    chosen.push({ system, priority })
  }

  const selected = systems.find((system) => system.id === selectedId)
  const hovered = systems.find((system) => system.id === hoveredId)
  push(selected, 0)
  push(hovered, 1)

  if (zoom > 1.2) {
    for (const system of systems) {
      if (system.capital) push(system, 2)
    }
  }

  if (zoom > 2.4) {
    const ranked = systems
      .filter((system) => system.kind === 'star')
      .slice()
      .sort((a, b) => (b.worldCount || 0) - (a.worldCount || 0) || a.token.localeCompare(b.token))
    for (const system of ranked) {
      if (chosen.length >= maxLabels) break
      push(system, 3)
    }
  }

  if (zoom > 4.5) {
    for (const system of systems) {
      if (chosen.length >= maxLabels) break
      if (system.kind === 'junction') continue
      push(system, 4)
    }
  }

  return chosen.slice(0, maxLabels)
}

export function estimateZoom(cameraDistance) {
  return Math.max(0.4, 8 / Math.max(cameraDistance, 0.35))
}

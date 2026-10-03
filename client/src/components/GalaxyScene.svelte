<script>
  import { onDestroy, onMount, untrack } from 'svelte'

  let {
    galaxy,
    selectedId = null,
    stormSnapshot = null,
    onSelect = undefined,
    onHover = undefined,
    onEnterSystem = undefined,
    onLabels = undefined,
    onViewportTiles = undefined,
    showPoliticalMap = true,
    locale = 'ru',
    focusRequest = null,
    resetToken = 0,
    ownershipRevision = 0,
  } = $props()

  let canvas = $state(null)
  let api = $state(null)
  let appliedOwnershipRevision = $state(0)
  let appliedSystemCount = $state(-1)
  let plateHydrated = $state(false)

  onMount(() => {
    let cancelled = false
    ;(async () => {
      const { createGalaxyScene } = await import('../lib/three/galaxyScene.js')
      if (cancelled || !galaxy || !canvas) return
      api = await createGalaxyScene(canvas, galaxy, {
        onSelect,
        onHover,
        onEnterSystem,
        onLabels,
        onViewportTiles,
        locale,
      })
      if (cancelled) {
        api?.dispose()
        api = null
        return
      }
      appliedOwnershipRevision = ownershipRevision
      appliedSystemCount = galaxy.systems?.length || 0
      plateHydrated = Boolean(galaxy?.meta?.systemsHydrated) || !galaxy?.tileGrid
      if (stormSnapshot) api.setStorms(stormSnapshot)
      api.setPoliticalMap(showPoliticalMap)
    })()
    return () => {
      cancelled = true
    }
  })

  onDestroy(() => {
    api?.dispose()
    api = null
  })

  $effect(() => {
    if (!api || !focusRequest) return
    const system = galaxy.byId.get(focusRequest.id)
    if (system) api.focusSystem(system, { enterSystem: !!focusRequest.enterSystem })
  })

  $effect(() => {
    if (!api) return
    void resetToken
    if (resetToken > 0) api.resetView()
  })

  $effect(() => {
    if (!api) return
    api.setSelected(selectedId)
  })

  $effect(() => {
    if (!api) return
    api.setStorms(stormSnapshot)
  })

  $effect(() => {
    if (!api) return
    api.setPoliticalMap(showPoliticalMap)
  })

  $effect(() => {
    if (!api) return
    api.setLocale(locale)
  })

  $effect(() => {
    if (!api) return
    const systems = galaxy?.systems || []
    if (systems.length === appliedSystemCount) return
    appliedSystemCount = systems.length
    api.setSystems(systems)
  })

  $effect(() => {
    if (!api) return
    api.setEdges(galaxy?.edgesDisplay || [])
  })

  $effect(() => {
    if (!api) return
    const revision = ownershipRevision
    const hydrated = Boolean(galaxy?.meta?.systemsHydrated) || !galaxy?.tileGrid
    if (revision === appliedOwnershipRevision && (plateHydrated || !hydrated)) return
    appliedOwnershipRevision = revision
    plateHydrated = hydrated
    if (!hydrated) return
    const currentGalaxy = untrack(() => galaxy)
    api.rebuildPoliticalOwnership(currentGalaxy)
  })
</script>

<canvas bind:this={canvas} class="galaxy-canvas" aria-label="3D galaxy map"></canvas>

<style>
  .galaxy-canvas {
    display: block;
    width: 100%;
    height: 100%;
    touch-action: none;
  }
</style>

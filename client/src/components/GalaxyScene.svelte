<script>
  import { onDestroy, onMount } from 'svelte'

  let {
    galaxy,
    selectedId = null,
    stormSnapshot = null,
    onSelect = undefined,
    onHover = undefined,
    onEnterSystem = undefined,
    onLabels = undefined,
    focusRequest = null,
    resetToken = 0,
  } = $props()

  let canvas = $state(null)
  let api = null

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
      })
      if (cancelled) {
        api?.dispose()
        api = null
        return
      }
      if (stormSnapshot) api.setStorms(stormSnapshot)
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

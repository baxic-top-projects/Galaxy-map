<script>
  import { onDestroy, tick } from 'svelte'

  let { detail = null } = $props()

  let canvas = $state(null)
  let api = null

  $effect(() => {
    const current = detail
    let cancelled = false
    api?.dispose()
    api = null
    if (!current) return

    tick().then(async () => {
      if (cancelled || !canvas) return
      const { createSystemDetailScene } = await import('../lib/three/detailScene.js')
      if (cancelled || !canvas) return
      api = createSystemDetailScene(canvas, current)
    })

    return () => {
      cancelled = true
      api?.dispose()
      api = null
    }
  })

  onDestroy(() => {
    api?.dispose()
    api = null
  })
</script>

{#if detail}
  <canvas bind:this={canvas} class="detail-canvas" aria-label="System detail view"></canvas>
{:else}
  <div class="empty">Выберите систему</div>
{/if}

<style>
  .detail-canvas,
  .empty {
    width: 100%;
    height: 100%;
    min-height: 280px;
    border-radius: 12px;
    background: radial-gradient(circle at 40% 30%, #15203a, #05070f 70%);
  }

  .empty {
    display: grid;
    place-items: center;
    color: #9bb0d0;
    font-family: 'Segoe UI', sans-serif;
  }
</style>

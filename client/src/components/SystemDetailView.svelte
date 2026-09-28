<script>
  import { onDestroy, tick } from 'svelte'

  let {
    detail = null,
    galaxy = null,
    locale = 'ru',
    onLabels = undefined,
    onZoomOut = undefined,
    onTravelTo = undefined,
  } = $props()

  let canvas = $state(null)
  let api = null
  let labels = $state([])

  $effect(() => {
    const current = detail
    const map = galaxy
    let cancelled = false
    api?.dispose()
    api = null
    labels = []
    if (!current) return

    tick().then(async () => {
      if (cancelled || !canvas) return
      const { createSystemDetailScene } = await import('../lib/three/detailScene.js')
      if (cancelled || !canvas) return
      api = createSystemDetailScene(canvas, current, {
        galaxy: map,
        onLabels(next) {
          labels = next
          onLabels?.(next)
        },
        onZoomOut,
        onTravelTo,
      })
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
  <div class="system-stage">
    <canvas bind:this={canvas} class="detail-canvas" aria-label="System detail view"></canvas>
    <div class="planet-labels" aria-hidden="true">
      {#each labels as label}
        {#if label.visible}
          <div
            class="planet-label"
            class:inhabited={label.inhabited}
            class:host={label.kind === 'star' || label.kind === 'black_hole' || label.kind === 'well' || label.kind === 'junction'}
            class:feature={label.kind === 'feature'}
            class:satellite={label.kind === 'satellite'}
            class:hyperlane={label.kind === 'hyperlane'}
            style={`left:${label.x}px;top:${label.y}px`}
          >
            <strong>{locale === 'en' ? label.nameEn : label.nameRu}</strong>
            {#if label.kind === 'hyperlane'}
              <span>{locale === 'en' ? 'Hyperlane' : 'Гиперкоридор'}</span>
            {:else if label.planetType}
              <span>{label.planetType}</span>
            {/if}
          </div>
        {/if}
      {/each}
    </div>
  </div>
{:else}
  <div class="empty">Загрузка системы…</div>
{/if}

<style>
  .system-stage,
  .empty {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 280px;
    background:
      linear-gradient(rgba(0, 0, 0, 0.68), rgba(0, 0, 0, 0.68)),
      #000 url('/textures/system_starfield.png?v=2') center / cover no-repeat;
  }

  .detail-canvas {
    display: block;
    width: 100%;
    height: 100%;
    background: transparent;
  }

  .empty {
    display: grid;
    place-items: center;
    color: #9bb0d0;
    font-family: 'Segoe UI', sans-serif;
  }

  .planet-labels {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  .planet-label {
    position: absolute;
    transform: translate(-50%, -130%);
    display: grid;
    gap: 0.1rem;
    padding: 0.25rem 0.55rem;
    border-radius: 10px;
    background: rgba(5, 10, 20, 0.72);
    border: 1px solid rgba(180, 210, 255, 0.2);
    white-space: nowrap;
    color: #d5e4ff;
  }

  .planet-label strong {
    font-size: 0.82rem;
  }

  .planet-label span {
    font-size: 0.68rem;
    color: #9bb0d0;
  }

  .planet-label.inhabited {
    border-color: rgba(140, 210, 255, 0.55);
    color: #ffffff;
  }

  .planet-label.host {
    border-color: rgba(255, 210, 120, 0.5);
    color: #ffe29a;
  }

  .planet-label.feature {
    border-color: rgba(210, 190, 120, 0.45);
    color: #e6d7a8;
  }

  .planet-label.satellite {
    border-color: rgba(185, 195, 215, 0.42);
    color: #d8deea;
    transform: translate(-50%, -115%) scale(0.88);
  }

  .planet-label.hyperlane {
    border-color: rgba(110, 190, 255, 0.55);
    color: #b8e0ff;
    background: rgba(8, 24, 48, 0.78);
  }
</style>

<script>
  import { onMount } from 'svelte'
  import GalaxyScene from './components/GalaxyScene.svelte'
  import MapHud from './components/MapHud.svelte'
  import SystemDetailView from './components/SystemDetailView.svelte'
  import { loadGalaxy, loadSystemDetail, systemLabel } from './lib/galaxy/loadGalaxy.js'
  import { estimateZoom } from './lib/galaxy/labelLod.js'

  let galaxy = $state(null)
  let error = $state('')
  let loading = $state(true)
  let locale = $state('ru')
  let selected = $state(null)
  let detail = $state(null)
  let polityFilter = $state('')
  let mode = $state('galaxy')
  let labels = $state([])
  let focusRequest = $state(null)
  let resetToken = $state(0)
  let zoom = $state(1)

  onMount(async () => {
    try {
      galaxy = await loadGalaxy()
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      loading = false
    }
  })

  $effect(() => {
    const current = selected
    if (!current) {
      detail = null
      return
    }
    let cancelled = false
    loadSystemDetail(current.shard)
      .then((data) => {
        if (!cancelled) detail = data
      })
      .catch(() => {
        if (!cancelled) detail = null
      })
    return () => {
      cancelled = true
    }
  })

  const visibleSystems = $derived.by(() => {
    if (!galaxy) return []
    if (!polityFilter) return galaxy.systems
    return galaxy.systems.filter((system) => system.stem === polityFilter)
  })

  const filteredGalaxy = $derived.by(() => {
    if (!galaxy) return null
    if (!polityFilter) return galaxy
    const systems = visibleSystems
    const ids = new Set(systems.map((system) => system.id))
    return {
      ...galaxy,
      systems,
      byId: new Map(systems.map((system) => [system.id, system])),
      edgesDisplay: galaxy.edgesDisplay.filter((edge) => ids.has(edge.a) && ids.has(edge.b)),
      edgesCanon: galaxy.edgesCanon.filter((edge) => ids.has(edge.a) && ids.has(edge.b)),
    }
  })

  function handleSelect(system) {
    selected = system
  }

  function handleSearchSelect(entry) {
    const system = galaxy?.byId.get(entry.id)
    if (!system) return
    selected = system
    focusRequest = { id: system.id, enterSystem: entry.kind === 'world' }
    if (entry.kind === 'world') mode = 'system'
  }

  function handleEnterSystem(system) {
    selected = system
    mode = 'system'
  }

  function handleLabels(nextLabels, nextZoom) {
    labels = nextLabels
    zoom = nextZoom ?? estimateZoom(8)
  }
</script>

{#if loading}
  <main class="boot">Загрузка галактики…</main>
{:else if error}
  <main class="boot error">{error}</main>
{:else if filteredGalaxy}
  <main class="app-shell">
    {#if mode === 'galaxy'}
      {#key polityFilter}
        <GalaxyScene
          galaxy={filteredGalaxy}
          selectedId={selected?.id || null}
          {focusRequest}
          {resetToken}
          onSelect={handleSelect}
          onEnterSystem={handleEnterSystem}
          onLabels={handleLabels}
        />
      {/key}

      <div class="labels" aria-hidden="true">
        {#each labels as label}
          {#if label.visible}
            <div
              class="label"
              class:capital={label.system.capital}
              class:selected={label.id === selected?.id}
              style={`left:${label.x}px;top:${label.y}px`}
            >
              {systemLabel(label.system, locale)}
            </div>
          {/if}
        {/each}
      </div>
    {:else}
      <section class="system-mode">
        <SystemDetailView {detail} />
      </section>
    {/if}

    <MapHud
      galaxy={filteredGalaxy}
      {locale}
      {selected}
      {detail}
      {polityFilter}
      {mode}
      onLocale={(value) => (locale = value)}
      onPolityFilter={(value) => {
        polityFilter = value
        selected = null
        mode = 'galaxy'
      }}
      onSearchSelect={handleSearchSelect}
      onReset={() => {
        mode = 'galaxy'
        selected = null
        resetToken += 1
      }}
      onBackToGalaxy={() => {
        mode = 'galaxy'
      }}
    />
  </main>
{/if}

<style>
  :global(:root) {
    color-scheme: dark;
    font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
    background: #05070f;
    color: #e8eef8;
  }

  :global(html),
  :global(body),
  :global(#app) {
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #05070f;
  }

  .boot {
    min-height: 100vh;
    display: grid;
    place-items: center;
    letter-spacing: 0.04em;
  }

  .boot.error {
    color: #ff8f8f;
    padding: 2rem;
    text-align: center;
  }

  .app-shell,
  .system-mode {
    position: relative;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background:
      radial-gradient(circle at 50% 45%, rgba(40, 70, 140, 0.28), transparent 42%),
      #05070f;
  }

  .system-mode {
    padding: 6.5rem 1rem 1rem;
    box-sizing: border-box;
  }

  .labels {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 3;
  }

  .label {
    position: absolute;
    transform: translate(-50%, -140%);
    padding: 0.15rem 0.4rem;
    border-radius: 999px;
    background: rgba(5, 10, 20, 0.55);
    border: 1px solid rgba(180, 210, 255, 0.18);
    font-size: 0.72rem;
    white-space: nowrap;
    color: #d5e4ff;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  }

  .label.capital {
    color: #ffe29a;
    border-color: rgba(255, 210, 120, 0.45);
  }

  .label.selected {
    color: #ffffff;
    border-color: rgba(120, 180, 255, 0.8);
    background: rgba(30, 70, 140, 0.55);
  }
</style>

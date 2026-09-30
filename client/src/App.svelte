<script>
  import { onDestroy, onMount } from 'svelte'
  import GalaxyScene from './components/GalaxyScene.svelte'
  import MapHud from './components/MapHud.svelte'
  import RealmMapPage from './components/RealmMapPage.svelte'
  import RealmNavigation from './components/RealmNavigation.svelte'
  import SystemDetailView from './components/SystemDetailView.svelte'
  import { loadGalaxy, loadSystemDetail, systemLabel } from './lib/galaxy/loadGalaxy.js'
  import { updateSystemOwner } from './lib/galaxy/ownershipApi.js'
  import { estimateZoom } from './lib/galaxy/labelLod.js'
  import { connectStormSocket, stormForSystem } from './lib/galaxy/stormsApi.js'
  import { fetchAssetManifest } from './lib/galaxy/assetsApi.js'
  import { applyAssetManifest, mapTexturePath } from './lib/galaxy/modelCatalog.js'
  import { pageFromPath } from './lib/realms/realmCatalog.js'

  let galaxy = $state(null)
  let error = $state('')
  let loading = $state(true)
  let locale = $state('ru')
  let page = $state(pageFromPath(window.location.pathname))
  let selected = $state(null)
  let detail = $state(null)
  let polityFilter = $state('')
  let mode = $state('galaxy')
  let labels = $state([])
  let showPoliticalMap = $state(true)
  let focusRequest = $state(null)
  let resetToken = $state(0)
  let zoom = $state(1)
  let stormSnapshot = $state(null)
  let stormStatus = $state('closed')
  let stormSocket = null
  let ownerSaving = $state(false)
  let ownerError = $state('')
  let ownershipRevision = $state(0)
  const starfieldUrl = $derived(mapTexturePath('system_starfield.png', 'v=2'))

  const selectedStorm = $derived(stormForSystem(stormSnapshot, selected?.id))

  function handleRouteChange() {
    page = pageFromPath(window.location.pathname)
  }

  function navigate(nextPage, path) {
    if (window.location.pathname !== path) window.history.pushState({}, '', path)
    page = nextPage
    if (nextPage === 'universe') mode = 'galaxy'
  }

  async function loadGalaxyWithRetry(attempts = 3) {
    let lastError
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        return await loadGalaxy()
      } catch (err) {
        lastError = err
        if (attempt + 1 < attempts) {
          await new Promise((resolve) => setTimeout(resolve, 750 * 2 ** attempt))
        }
      }
    }
    throw lastError
  }

  onMount(async () => {
    window.addEventListener('popstate', handleRouteChange)
    fetchAssetManifest()
      .then((manifest) => applyAssetManifest(manifest))
      .catch(() => {
        // Keep local /models fallbacks when asset-service is unavailable.
      })
    try {
      galaxy = await loadGalaxyWithRetry()
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      loading = false
    }

    stormSocket = connectStormSocket({
      onSnapshot(snapshot) {
        stormSnapshot = snapshot
      },
      onStatus(status) {
        stormStatus = status
      },
    })
  })

  onDestroy(() => {
    window.removeEventListener('popstate', handleRouteChange)
    stormSocket?.close()
    stormSocket = null
  })

  $effect(() => {
    const current = selected
    if (!current) {
      detail = null
      return
    }
    let cancelled = false
    loadSystemDetail(current)
      .then((data) => {
        if (!cancelled) {
          detail = {
            ...data,
            canonicalStem: data.stem,
            stem: current.stem,
          }
        }
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
    ownerError = ''
  }

  function handleEnterSystem(system) {
    selected = system
    ownerError = ''
    mode = 'system'
  }

  async function handleSearchSelect(entry) {
    const system = galaxy?.byId.get(entry.id)
    if (!system) return
    selected = system
    ownerError = ''
    focusRequest = { id: system.id, enterSystem: true }
    mode = 'system'
  }

  function applyOwnerLocally(systemId, stem) {
    if (!galaxy) return null
    const current = galaxy.byId.get(systemId)
    if (!current) return null
    const nextSystem = {
      ...current,
      canonicalStem: current.canonicalStem || current.stem,
      stem,
    }
    const systems = galaxy.systems.map((system) =>
      system.id === systemId ? nextSystem : system,
    )
    const search = galaxy.search.map((entry) =>
      entry.id === systemId ? { ...entry, stem } : entry,
    )
    galaxy = {
      ...galaxy,
      systems,
      search,
      byId: new Map(systems.map((system) => [system.id, system])),
    }
    return nextSystem
  }

  async function handleOwnerChange(system, stem) {
    if (!system || !stem || system.stem === stem || ownerSaving) return
    ownerSaving = true
    ownerError = ''
    const previousStem = system.stem
    const optimistic = applyOwnerLocally(system.id, stem)
    if (optimistic) selected = optimistic
    if (detail?.id === system.id) {
      detail = {
        ...detail,
        canonicalStem: detail.canonicalStem || detail.stem,
        stem,
      }
    }
    ownershipRevision += 1
    try {
      await updateSystemOwner(system.id, stem)
    } catch (err) {
      applyOwnerLocally(system.id, previousStem)
      if (selected?.id === system.id) {
        selected = galaxy?.byId.get(system.id) || selected
      }
      if (detail?.id === system.id) {
        detail = { ...detail, stem: previousStem }
      }
      ownershipRevision += 1
      ownerError = err instanceof Error ? err.message : String(err)
    } finally {
      ownerSaving = false
    }
  }

  function handleLabels(nextLabels, nextZoom) {
    labels = nextLabels
    zoom = nextZoom ?? estimateZoom(8)
  }

</script>

{#if page !== 'universe'}
  <RealmMapPage realmId={page} {locale} />
{:else if loading}
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
          {stormSnapshot}
          {showPoliticalMap}
          {locale}
          ownershipRevision={ownershipRevision}
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
      <section class="system-mode" style={`--starfield:url('${starfieldUrl}')`}>
        <SystemDetailView
          {detail}
          {galaxy}
          {locale}
          storm={selectedStorm}
          onZoomOut={() => {
            mode = 'galaxy'
            resetToken += 1
          }}
          onTravelTo={handleEnterSystem}
        />
      </section>
    {/if}

    <MapHud
      galaxy={filteredGalaxy}
      {locale}
      {selected}
      {detail}
      {polityFilter}
      {mode}
      {showPoliticalMap}
      {ownerSaving}
      {ownerError}
      storm={selectedStorm}
      stormCount={stormSnapshot?.storms?.length || 0}
      {stormStatus}
      onLocale={(value) => (locale = value)}
      onPoliticalMap={(value) => (showPoliticalMap = value)}
      onPolityFilter={(value) => {
        polityFilter = value
        selected = null
        mode = 'galaxy'
      }}
      onOwnerChange={handleOwnerChange}
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

<RealmNavigation
  current={page}
  {locale}
  onNavigate={navigate}
/>

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
  }

  .app-shell {
    background:
      radial-gradient(circle at 50% 45%, rgba(40, 70, 140, 0.28), transparent 42%),
      #05070f;
  }

  .system-mode {
    padding: 0;
    box-sizing: border-box;
    background:
      linear-gradient(rgba(0, 0, 0, 0.68), rgba(0, 0, 0, 0.68)),
      #000 var(--starfield) center / cover no-repeat;
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

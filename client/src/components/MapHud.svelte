<script>
  import { filterSearch } from '../lib/galaxy/search.js'
  import { polityLabel, systemLabel } from '../lib/galaxy/loadGalaxy.js'
  import UserMenu from './UserMenu.svelte'

  let {
    galaxy,
    locale = 'ru',
    selected = null,
    detail = null,
    polityFilter = '',
    onLocale = undefined,
    onSearchSelect = undefined,
    onPolityFilter = undefined,
    onOwnerChange = undefined,
    ownerSaving = false,
    ownerError = '',
    onReset = undefined,
    onBackToGalaxy = undefined,
    onPoliticalMap = undefined,
    showPoliticalMap = true,
    user = null,
    onLogin = undefined,
    onRegister = undefined,
    onProfile = undefined,
    onAdmin = undefined,
    onLogout = undefined,
    mode = 'galaxy',
  } = $props()

  let query = $state('')
  let results = $derived(
    filterSearch(galaxy?.search || [], query, {
      locale,
      limit: 12,
      stem: polityFilter || null,
    }),
  )

  const selectedPolity = $derived(
    selected?.stem ? galaxy.polityByStem.get(selected.stem) : null,
  )
  const canEditOwner = $derived(
    user?.role === 'ADMIN' && !!selected && selected.kind !== 'well',
  )
</script>

<header class="hud-top">
  <div class="brand">
    <div class="title">The Universe</div>
    <div class="subtitle">
      {locale === 'en' ? 'Interactive galaxy map' : 'Интерактивная карта галактики'}
    </div>
  </div>

  <div class="controls">
    <label class="search">
      <span class="sr-only">Поиск</span>
      <input
        bind:value={query}
        placeholder={locale === 'en' ? 'Search stars and worlds…' : 'Поиск звёзд и миров…'}
      />
      {#if results.length}
        <ul class="results">
          {#each results as entry}
            <li>
              <button type="button" onclick={() => onSearchSelect?.(entry)}>
                <strong>{locale === 'en' ? entry.nameEn : entry.nameRu}</strong>
                <span>{entry.kind === 'world' ? (locale === 'en' ? 'world' : 'мир') : (locale === 'en' ? 'system' : 'система')}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </label>

    <select
      value={polityFilter}
      onchange={(event) => onPolityFilter?.(event.currentTarget.value)}
      aria-label="Polity filter"
    >
      <option value="">{locale === 'en' ? 'All polities' : 'Все державы'}</option>
      {#each galaxy?.polities || [] as polity}
        <option value={polity.stem}>{polityLabel(polity, locale)}</option>
      {/each}
    </select>

    <button type="button" class="ghost" onclick={() => onLocale?.(locale === 'ru' ? 'en' : 'ru')}>
      {locale === 'ru' ? 'EN' : 'RU'}
    </button>
    <button type="button" class="ghost" onclick={() => onReset?.()}>
      {locale === 'en' ? 'Reset view' : 'Сброс'}
    </button>
    {#if mode === 'galaxy'}
      <button
        type="button"
        class="ghost"
        class:active={showPoliticalMap}
        aria-pressed={showPoliticalMap}
        onclick={() => onPoliticalMap?.(!showPoliticalMap)}
      >
        {locale === 'en'
          ? `Political map: ${showPoliticalMap ? 'on' : 'off'}`
          : `Политкарта: ${showPoliticalMap ? 'вкл' : 'выкл'}`}
      </button>
    {/if}
    {#if mode === 'system'}
      <button type="button" class="primary" onclick={() => onBackToGalaxy?.()}>
        {locale === 'en' ? 'Galaxy view' : 'К галактике'}
      </button>
    {/if}
    <UserMenu {user} {locale} {onLogin} {onRegister} {onProfile} {onAdmin} {onLogout} />
  </div>
</header>

<aside class="panel">
  {#if selected}
    <h2>{systemLabel(selected, locale)}</h2>
    <p class="meta">
      {#if selected.kind !== 'junction'}
        {selected.token}
      {/if}
      {#if selectedPolity}
        {selected.kind !== 'junction' ? ' · ' : ''}{polityLabel(selectedPolity, locale)}
      {/if}
    </p>
    {#if canEditOwner}
      <label class="owner">
        <span>{locale === 'en' ? 'Owner polity' : 'Держава-владелец'}</span>
        <select
          value={selected.stem || ''}
          disabled={ownerSaving}
          onchange={(event) => onOwnerChange?.(selected, event.currentTarget.value)}
          aria-label={locale === 'en' ? 'Owner polity' : 'Держава-владелец'}
        >
          {#each galaxy?.polities || [] as polity}
            <option value={polity.stem}>{polityLabel(polity, locale)}</option>
          {/each}
        </select>
        {#if ownerSaving}
          <small>{locale === 'en' ? 'Saving…' : 'Сохранение…'}</small>
        {:else if ownerError}
          <small class="error">{ownerError}</small>
        {/if}
      </label>
    {/if}
    {#if detail}
      <dl>
        <div>
          <dt>{locale === 'en' ? 'Object' : 'Объект'}</dt>
          <dd>
            {#if detail.kind === 'black_hole'}
              {locale === 'en' ? 'Black hole system' : 'Система чёрной дыры'}
            {:else if detail.kind === 'well'}
              {locale === 'en' ? 'Galactic core' : 'Галактическое ядро'}
            {:else if detail.kind === 'junction'}
              {locale === 'en' ? 'Hypercorridor junction' : 'Стык гиперкоридоров'}
            {:else}
              {locale === 'en' ? 'Star system' : 'Звёздная система'}
            {/if}
          </dd>
        </div>
        <div>
          <dt>
            {detail.kind === 'junction'
              ? (locale === 'en' ? 'Node type' : 'Тип узла')
              : (locale === 'en' ? 'Star / hole type' : 'Тип звезды / дыры')}
          </dt>
          <dd>{detail.starType}</dd>
        </div>
        {#if detail.sectorNameEn}
          <div>
            <dt>{locale === 'en' ? 'Sector' : 'Сектор'}</dt>
            <dd>{detail.sectorNameEn}</dd>
          </div>
        {/if}
        <div>
          <dt>{locale === 'en' ? 'Inhabited worlds' : 'Обитаемые миры'}</dt>
          <dd>{detail.worlds?.length || 0}</dd>
        </div>
        <div>
          <dt>{locale === 'en' ? 'Uninhabited bodies' : 'Необитаемые тела'}</dt>
          <dd>{detail.uninhabited?.length || 0}</dd>
        </div>
      </dl>

      {#if detail.worlds?.length}
        <h3>{locale === 'en' ? 'Named worlds' : 'Именованные миры'}</h3>
        <ul class="worlds">
          {#each detail.worlds as world}
            <li>
              <strong>{locale === 'en' ? world.nameEn : world.nameRu}</strong>
              <span>{world.planetType}</span>
            </li>
          {/each}
        </ul>
      {/if}

      {#if detail.worlds?.some((world) => world.satellites?.length)}
        <h3>{locale === 'en' ? 'Natural satellites' : 'Естественные спутники'}</h3>
        <ul class="worlds">
          {#each detail.worlds as world}
            {#each world.satellites || [] as satellite}
              <li>
                <strong>{locale === 'en' ? satellite.nameEn : satellite.nameRu}</strong>
                <span>{satellite.planetType}</span>
              </li>
            {/each}
          {/each}
        </ul>
      {/if}

      {#if detail.uninhabited?.length}
        <h3>{locale === 'en' ? 'Uninhabited planets' : 'Необитаемые планеты'}</h3>
        <ul class="worlds">
          {#each detail.uninhabited as body}
            <li>
              <strong>{locale === 'en' ? body.nameEn : body.nameRu}</strong>
              <span>{body.planetType}</span>
            </li>
          {/each}
        </ul>
      {/if}

      {#if detail.features?.length}
        <h3>{locale === 'en' ? 'System features' : 'Особенности системы'}</h3>
        <ul class="worlds">
          {#each detail.features as feature}
            <li>
              <strong>{locale === 'en' ? feature.nameEn : feature.nameRu}</strong>
              <span>{feature.feature}</span>
            </li>
          {/each}
        </ul>
      {/if}

      {#if detail.kind === 'junction'}
        <p class="hint">
          {locale === 'en'
            ? 'No star or planets: hypercorridors intersect here. Asteroid belts may be present.'
            : 'Здесь нет звезды и планет: в этой точке стыкуются гиперкоридоры. Возможны астероидные пояса.'}
        </p>
      {:else if detail.kind === 'black_hole' || detail.kind === 'well'}
        <p class="hint">
          {locale === 'en'
            ? 'This system has no counted worlds — only the black hole itself.'
            : 'В этой системе нет учтённых миров — только сама чёрная дыра.'}
        </p>
      {/if}
    {:else}
      <p class="hint">{locale === 'en' ? 'Loading system dossier…' : 'Загрузка карточки системы…'}</p>
    {/if}
    <p class="hint">
      {locale === 'en'
        ? 'Double-click a star, black hole, or junction to enter its system.'
        : 'Двойной клик по звезде, чёрной дыре или стыку открывает систему.'}
    </p>
  {:else}
    <h2>{locale === 'en' ? 'Galaxy overview' : 'Обзор галактики'}</h2>
    <p class="meta">
      {galaxy?.meta?.systemCount || 0}
      {locale === 'en' ? 'systems' : 'систем'} ·
      {galaxy?.meta?.edgeCountDisplay || 0}
      {locale === 'en' ? 'lanes' : 'коридоров'}
    </p>
    <p class="hint">
      {locale === 'en'
        ? 'Drag to orbit, scroll to zoom, click to select.'
        : 'Тяните для орбиты, колёсико — зум, клик — выбор.'}
    </p>
  {/if}
</aside>

<style>
  .hud-top,
  .panel {
    position: absolute;
    z-index: 5;
    color: #e8eef8;
    font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
    pointer-events: none;
  }

  .hud-top {
    top: 1rem;
    left: 1rem;
    right: 1rem;
    z-index: 20;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .brand,
  .controls,
  .panel,
  .search,
  .results,
  button,
  select,
  input {
    pointer-events: auto;
  }

  .title {
    font-size: 1.35rem;
    letter-spacing: 0.04em;
    font-weight: 700;
    text-shadow: 0 2px 18px rgba(0, 0, 0, 0.65);
  }

  .subtitle,
  .meta,
  .hint,
  .worlds span,
  .results span {
    color: #9bb0d0;
  }

  .controls {
    display: flex;
    gap: 0.55rem;
    flex-wrap: wrap;
    justify-content: flex-end;
    min-width: 0;
  }

  .search {
    position: relative;
    min-width: min(320px, 70vw);
    max-width: 100%;
  }

  input,
  select,
  button {
    box-sizing: border-box;
    border: 1px solid rgba(170, 200, 255, 0.25);
    background: rgba(8, 14, 28, 0.82);
    color: inherit;
    border-radius: 10px;
    padding: 0.55rem 0.8rem;
    font: inherit;
  }

  input {
    width: 100%;
  }

  button {
    cursor: pointer;
  }

  button.primary {
    background: linear-gradient(180deg, #3d6dff, #2448b8);
    border-color: transparent;
  }

  button.ghost:hover,
  button.ghost.active,
  select:hover,
  input:focus {
    border-color: rgba(190, 220, 255, 0.55);
  }

  .results {
    position: absolute;
    top: calc(100% + 0.35rem);
    left: 0;
    right: 0;
    margin: 0;
    padding: 0.35rem;
    list-style: none;
    background: rgba(8, 14, 28, 0.95);
    border: 1px solid rgba(170, 200, 255, 0.2);
    border-radius: 12px;
    max-height: 280px;
    overflow: auto;
  }

  .results button {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    background: transparent;
    border: 0;
    border-radius: 8px;
    text-align: left;
  }

  .results button:hover {
    background: rgba(70, 110, 180, 0.25);
  }

  .panel {
    top: 6.5rem;
    right: 1rem;
    width: min(320px, calc(100vw - 2rem));
    padding: 1rem 1.1rem;
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(10, 16, 32, 0.88), rgba(8, 12, 24, 0.72));
    border: 1px solid rgba(170, 200, 255, 0.18);
    backdrop-filter: blur(10px);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
  }

  .panel h2,
  .panel h3 {
    margin: 0 0 0.35rem;
  }

  .panel h3 {
    margin-top: 0.9rem;
    font-size: 0.95rem;
  }

  .owner {
    display: grid;
    gap: 0.35rem;
    margin: 0.75rem 0 0;
    font-size: 0.82rem;
    color: #8ea4c7;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .owner select {
    width: 100%;
    text-transform: none;
    letter-spacing: normal;
    color: #e8eef8;
  }

  .owner small {
    text-transform: none;
    letter-spacing: normal;
    color: #9bb0d0;
  }

  .owner .error {
    color: #ff8f8f;
  }

  dl {
    display: grid;
    gap: 0.45rem;
    margin: 0.8rem 0 0;
  }

  dt {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #8ea4c7;
  }

  dd {
    margin: 0.1rem 0 0;
  }

  .worlds {
    list-style: none;
    margin: 0.4rem 0 0;
    padding: 0;
    display: grid;
    gap: 0.35rem;
  }

  .worlds li {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    font-size: 0.92rem;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  @media (max-width: 820px) {
    .panel {
      top: auto;
      bottom: 1rem;
      right: 1rem;
      left: 1rem;
      width: auto;
      max-height: 38vh;
      overflow: auto;
    }
  }
</style>

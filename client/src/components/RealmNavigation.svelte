<script>
  import { REALMS } from '../lib/realms/realmCatalog.js'

  let {
    current = 'universe',
    locale = 'ru',
    onNavigate = undefined,
  } = $props()

  const items = [
    { id: 'universe', path: '/', nameRu: 'Вселенная', nameEn: 'Universe' },
    ...Object.entries(REALMS).map(([id, realm]) => ({ id, ...realm })),
  ]
</script>

<nav class="realm-nav" aria-label={locale === 'en' ? 'World maps' : 'Карты миров'}>
  {#each items as item}
    <button
      type="button"
      class:active={current === item.id}
      aria-current={current === item.id ? 'page' : undefined}
      onclick={() => onNavigate?.(item.id, item.path)}
    >
      {locale === 'en' ? item.nameEn : item.nameRu}
    </button>
  {/each}
</nav>

<style>
  .realm-nav {
    position: fixed;
    z-index: 20;
    left: 50%;
    bottom: 1rem;
    transform: translateX(-50%);
    display: flex;
    gap: 0.3rem;
    padding: 0.35rem;
    border: 1px solid rgba(170, 205, 255, 0.2);
    border-radius: 999px;
    background: rgba(4, 8, 18, 0.82);
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(14px);
  }

  button {
    border: 1px solid transparent;
    border-radius: 999px;
    padding: 0.45rem 0.78rem;
    background: transparent;
    color: #9fb0c9;
    font: inherit;
    font-size: 0.76rem;
    cursor: pointer;
  }

  button:hover {
    color: #fff;
    background: rgba(125, 170, 235, 0.12);
  }

  button.active {
    color: #fff;
    border-color: rgba(145, 195, 255, 0.42);
    background: rgba(70, 125, 205, 0.3);
  }

  @media (max-width: 680px) {
    .realm-nav {
      bottom: 0.55rem;
      max-width: calc(100vw - 1rem);
      overflow-x: auto;
    }

    button {
      padding-inline: 0.62rem;
    }
  }
</style>


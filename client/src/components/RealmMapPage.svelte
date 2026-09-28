<script>
  import { REALMS } from '../lib/realms/realmCatalog.js'

  let { realmId, locale = 'ru' } = $props()
  const realm = $derived(REALMS[realmId] || REALMS.void)
</script>

<main
  class="realm-page"
  style={`--accent:${realm.accent};--glow:${realm.glow};--realm-bg:${realm.background}`}
>
  <div class="map-surface" aria-label={locale === 'en' ? `${realm.nameEn} map` : `Карта: ${realm.nameRu}`}>
    <div class="realm-haze"></div>
    <div class="map-grid"></div>
    <div class="origin-marker" aria-hidden="true">
      <span></span>
    </div>
  </div>

  <header>
    <p>{locale === 'en' ? 'Separate plane' : 'Отдельный план'}</p>
    <h1>{locale === 'en' ? realm.nameEn : realm.nameRu}</h1>
    <span>{locale === 'en' ? realm.subtitleEn : realm.subtitleRu}</span>
  </header>

  <aside>
    <strong>{locale === 'en' ? 'Map layer' : 'Слой карты'}</strong>
    <p>
      {locale === 'en'
        ? 'This plane has an independent map and data source.'
        : 'У этого плана будет независимая карта и собственный источник данных.'}
    </p>
  </aside>
</main>

<style>
  .realm-page {
    position: relative;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    color: var(--accent);
    background: var(--realm-bg);
  }

  .map-surface,
  .realm-haze,
  .map-grid {
    position: absolute;
    inset: 0;
  }

  .map-surface {
    background:
      radial-gradient(circle at 50% 48%, color-mix(in srgb, var(--glow) 18%, transparent), transparent 34%),
      radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--glow) 9%, transparent), transparent 24%),
      var(--realm-bg);
  }

  .realm-haze {
    background:
      radial-gradient(ellipse at 62% 38%, color-mix(in srgb, var(--glow) 13%, transparent), transparent 34%),
      radial-gradient(ellipse at 35% 70%, color-mix(in srgb, var(--accent) 8%, transparent), transparent 30%);
    filter: blur(30px);
  }

  .map-grid {
    opacity: 0.18;
    background-image:
      linear-gradient(color-mix(in srgb, var(--accent) 18%, transparent) 1px, transparent 1px),
      linear-gradient(90deg, color-mix(in srgb, var(--accent) 18%, transparent) 1px, transparent 1px);
    background-size: 64px 64px;
    mask-image: radial-gradient(circle at center, black, transparent 78%);
  }

  header {
    position: absolute;
    top: 1.2rem;
    left: 1.2rem;
    z-index: 2;
  }

  header p {
    margin: 0 0 0.3rem;
    color: color-mix(in srgb, var(--accent) 62%, #8390a6);
    font-size: 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    color: var(--accent);
    font-size: clamp(1.6rem, 3vw, 2.8rem);
    text-shadow: 0 0 22px color-mix(in srgb, var(--glow) 55%, transparent);
  }

  header span {
    display: block;
    margin-top: 0.25rem;
    color: color-mix(in srgb, var(--accent) 68%, #8290a5);
    font-size: 0.82rem;
  }

  aside {
    position: absolute;
    z-index: 2;
    top: 1.2rem;
    right: 1.2rem;
    width: min(17rem, calc(100vw - 2.4rem));
    box-sizing: border-box;
    padding: 1rem;
    border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
    border-radius: 14px;
    background: color-mix(in srgb, var(--realm-bg) 82%, transparent);
    backdrop-filter: blur(12px);
  }

  aside strong {
    font-size: 0.82rem;
  }

  aside p {
    margin: 0.45rem 0 0;
    color: color-mix(in srgb, var(--accent) 62%, #7f899c);
    font-size: 0.76rem;
    line-height: 1.45;
  }

  .origin-marker {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 7rem;
    height: 7rem;
    transform: translate(-50%, -50%);
    border: 1px solid color-mix(in srgb, var(--accent) 32%, transparent);
    border-radius: 50%;
    box-shadow:
      0 0 35px color-mix(in srgb, var(--glow) 25%, transparent),
      inset 0 0 28px color-mix(in srgb, var(--glow) 14%, transparent);
  }

  .origin-marker::before,
  .origin-marker::after {
    content: '';
    position: absolute;
    background: color-mix(in srgb, var(--accent) 34%, transparent);
  }

  .origin-marker::before {
    top: 50%;
    left: -2rem;
    width: 11rem;
    height: 1px;
  }

  .origin-marker::after {
    top: -2rem;
    left: 50%;
    width: 1px;
    height: 11rem;
  }

  .origin-marker span {
    position: absolute;
    inset: 42%;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 18px var(--glow);
  }
</style>


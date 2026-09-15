<script>
  let count = 0
</script>

<main>
  <a href="https://svelte.dev" target="_blank" rel="noreferrer" aria-label="Svelte">
    <svg class="logo" viewBox="0 0 256 308" aria-hidden="true">
      <path
        fill="#ff3e00"
        d="M239.7 40.7C211.1-.2 154.7-12.3 113.9 13.7L42.2 59.4A82.2 82.2 0 0 0 5.1 114.4a86.6 86.6 0 0 0 8.5 55.6A82.4 82.4 0 0 0 1.4 200.7a87.6 87.6 0 0 0 15 66.2c28.6 40.9 85 53 125.8 27l71.6-45.6a82.2 82.2 0 0 0 37.1-55.1 86.6 86.6 0 0 0-8.5-55.5 82.4 82.4 0 0 0 12.3-30.7 87.6 87.6 0 0 0-15-66.3"
      />
    </svg>
  </a>

  <h1>Svelte</h1>

  <section class="card">
    <button onclick={() => count += 1}>count is {count}</button>
    <p>Edit <code>src/App.svelte</code> to get started</p>
  </section>

  <p class="hint">Click on the Svelte logo to learn more</p>
</main>

<style>
  :global(:root) {
    font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
    line-height: 1.5;
    color: rgba(255, 255, 255, 0.87);
    background: #242424;
    font-synthesis: none;
    text-rendering: optimizeLegibility;
  }

  :global(body) {
    margin: 0;
    min-width: 320px;
    min-height: 100vh;
  }

  main {
    max-width: 1280px;
    margin: 0 auto;
    padding: 2rem;
    text-align: center;
  }

  .logo {
    width: 6em;
    height: 6em;
    padding: 1.5em;
    transition: filter 300ms;
  }

  .logo:hover {
    filter: drop-shadow(0 0 2em #ff3e00aa);
  }

  .card {
    padding: 2em;
  }

  button {
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0.6em 1.2em;
    font: inherit;
    font-weight: 500;
    background: #1a1a1a;
    cursor: pointer;
  }

  button:hover {
    border-color: #ff3e00;
  }

  .hint {
    color: #888;
  }

  @media (prefers-color-scheme: light) {
    :global(:root) {
      color: #213547;
      background: #fff;
    }

    button {
      background: #f9f9f9;
    }
  }
</style>

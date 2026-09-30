<script>
  let {
    user = null,
    locale = 'ru',
    onLogin = undefined,
    onProfile = undefined,
    onAdmin = undefined,
    onLogout = undefined,
  } = $props()

  let open = $state(false)
  let root

  function onDocumentPointer(event) {
    if (open && root && !root.contains(event.target)) open = false
  }

  function onDocumentKey(event) {
    if (event.key === 'Escape') open = false
  }

  $effect(() => {
    document.addEventListener('pointerdown', onDocumentPointer)
    document.addEventListener('keydown', onDocumentKey)
    return () => {
      document.removeEventListener('pointerdown', onDocumentPointer)
      document.removeEventListener('keydown', onDocumentKey)
    }
  })

  function choose(action) {
    open = false
    action?.()
  }
</script>

<div class="account" bind:this={root}>
  {#if !user}
    <button class="login" type="button" onclick={() => onLogin?.()}>
      {locale === 'en' ? 'Sign in' : 'Войти'}
    </button>
  {:else}
    <button
      class="user"
      type="button"
      aria-haspopup="menu"
      aria-expanded={open}
      onclick={() => (open = !open)}
    >
      {#if user.avatar_url || user.avatarUrl}
        <img src={user.avatar_url || user.avatarUrl} alt="" />
      {:else}
        <span class="fallback">{(user.display_name || user.displayName || user.email || '?')[0]}</span>
      {/if}
      <span>{user.display_name || user.displayName || user.email}</span>
    </button>
    {#if open}
      <div class="menu" role="menu">
        <button role="menuitem" type="button" onclick={() => choose(onProfile)}>
          {locale === 'en' ? 'Profile' : 'Профиль'}
        </button>
        {#if user.role === 'ADMIN'}
          <button role="menuitem" type="button" onclick={() => choose(onAdmin)}>
            {locale === 'en' ? 'Role management' : 'Управление ролями'}
          </button>
        {/if}
        <button role="menuitem" class="danger" type="button" onclick={() => choose(onLogout)}>
          Logout
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .account { position: relative; }
  button {
    color: #e8eef8;
    border: 1px solid rgba(150, 190, 255, 0.28);
    background: rgba(7, 14, 28, 0.9);
    cursor: pointer;
  }
  .login { border-radius: 8px; padding: 0.55rem 0.85rem; }
  .user {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    border-radius: 999px;
    padding: 0.28rem 0.7rem 0.28rem 0.3rem;
  }
  img, .fallback {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    object-fit: cover;
  }
  .fallback {
    display: grid;
    place-items: center;
    background: #365c91;
    font-weight: 700;
    text-transform: uppercase;
  }
  .menu {
    position: absolute;
    z-index: 30;
    right: 0;
    top: calc(100% + 0.45rem);
    width: 190px;
    padding: 0.35rem;
    border-radius: 10px;
    border: 1px solid rgba(150, 190, 255, 0.22);
    background: rgba(8, 13, 24, 0.98);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  }
  .menu button {
    width: 100%;
    border: 0;
    border-radius: 7px;
    padding: 0.65rem 0.7rem;
    text-align: left;
  }
  .menu button:hover { background: rgba(100, 150, 220, 0.18); }
  .menu .danger { color: #ff9c9c; }
</style>

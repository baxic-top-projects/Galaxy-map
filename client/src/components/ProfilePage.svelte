<script>
  import { deleteAvatar, updateProfile, uploadAvatar } from '../lib/auth/authApi.js'
  import { createPanelDrag, loadPanelPos } from '../lib/ui/panelDrag.js'

  const PANEL_POS_KEY = 'profile-page'

  let {
    user,
    locale = 'ru',
    onUpdated = undefined,
    onBack = undefined,
  } = $props()

  let displayName = $state('')
  let busy = $state(false)
  let error = $state('')
  let notice = $state('')
  let panelPos = $state(loadPanelPos(PANEL_POS_KEY))
  let panelDragging = $state(false)

  const panelDrag = createPanelDrag(
    () => panelPos,
    (pos) => {
      panelPos = pos
    },
    PANEL_POS_KEY,
    {
      onActive(active) {
        panelDragging = active
      },
    },
  )

  $effect(() => {
    displayName = user?.display_name || user?.displayName || ''
  })

  function onHeadPointerDown(event) {
    panelDrag.onPointerDown(event)
  }

  async function save() {
    busy = true
    error = ''
    try {
      const updated = await updateProfile({ display_name: displayName })
      onUpdated?.(updated?.user || updated)
      notice = locale === 'en' ? 'Profile saved.' : 'Профиль сохранён.'
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
    }
  }

  async function chooseAvatar(event) {
    const file = event.currentTarget.files?.[0]
    if (!file) return
    busy = true
    error = ''
    try {
      const updated = await uploadAvatar(file)
      onUpdated?.(updated?.user || updated)
      notice = locale === 'en' ? 'Avatar updated.' : 'Аватар обновлён.'
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
      event.currentTarget.value = ''
    }
  }

  async function removeAvatar() {
    busy = true
    error = ''
    try {
      const updated = await deleteAvatar()
      onUpdated?.(updated?.user || updated)
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
    }
  }
</script>

<main class="page">
  <section
    class="profile"
    class:dragging={panelDragging}
    style="transform: translate3d({panelPos.x}px, {panelPos.y}px, 0)"
  >
    <div
      class="profile-head"
      role="presentation"
      title={locale === 'en' ? 'Drag to move' : 'Перетащите, чтобы переместить'}
      onpointerdown={onHeadPointerDown}
    >
      <button class="back" type="button" onclick={() => onBack?.()}>
        ← {locale === 'en' ? 'Back to map' : 'Назад к карте'}
      </button>
      <h1>{locale === 'en' ? 'Profile' : 'Профиль'}</h1>
    </div>
    <div class="identity">
      {#if user?.avatar_url || user?.avatarUrl}
        <img src={user.avatar_url || user.avatarUrl} alt="" />
      {:else}
        <div class="avatar">{(user?.display_name || user?.email || '?')[0]}</div>
      {/if}
      <div>
        <strong>{user?.display_name || user?.displayName || user?.email}</strong>
        <span>{user?.email}</span>
        <span class="role">{user?.role}</span>
      </div>
    </div>
    <label>
      <span>{locale === 'en' ? 'Display name' : 'Имя'}</span>
      <input bind:value={displayName} minlength="2" />
    </label>
    <button class="primary" type="button" disabled={busy} onclick={save}>{locale === 'en' ? 'Save' : 'Сохранить'}</button>
    <div class="avatar-actions">
      <label class="upload">
        {locale === 'en' ? 'Upload avatar' : 'Загрузить аватар'}
        <input type="file" accept="image/png,image/jpeg,image/webp" onchange={chooseAvatar} />
      </label>
      {#if user?.avatar_url || user?.avatarUrl}
        <button type="button" disabled={busy} onclick={removeAvatar}>{locale === 'en' ? 'Remove avatar' : 'Удалить аватар'}</button>
      {/if}
    </div>
    <p class="hint">{locale === 'en' ? 'PNG, JPEG or WebP. Maximum 5 MB.' : 'PNG, JPEG или WebP. Максимум 5 МБ.'}</p>
    {#if error}<p class="error">{error}</p>{/if}
    {#if notice}<p class="notice">{notice}</p>{/if}
  </section>
</main>

<style>
  .page { min-height: 100vh; display: grid; place-items: center; padding: 1rem; background: #05070f; }
  .profile {
    width: min(560px, 100%);
    padding: 1.6rem;
    border-radius: 16px;
    border: 1px solid rgba(150,190,255,.2);
    background: #09111f;
  }
  .profile-head {
    margin: -0.35rem -0.35rem 0.35rem;
    padding: 0.55rem 0.35rem;
    cursor: grab;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .profile.dragging,
  .profile.dragging .profile-head {
    cursor: grabbing;
  }
  .back { border: 0; background: transparent; color: #aac9f2; cursor: pointer; }
  .profile-head h1 { margin: 0.35rem 0 0; }
  .identity { display: flex; gap: 1rem; align-items: center; margin: 1.2rem 0; }
  .identity img, .avatar { width: 86px; height: 86px; border-radius: 50%; object-fit: cover; }
  .avatar { display: grid; place-items: center; background: #315d96; font-size: 2rem; font-weight: 700; }
  .identity div:last-child { display: grid; gap: .25rem; }
  .identity span { color: #9cacbf; }
  .role { color: #ffd78b !important; }
  label { display: grid; gap: .4rem; }
  input { padding: .75rem; border: 1px solid rgba(150,190,255,.24); border-radius: 8px; color: #fff; background: #101a2b; }
  .primary, .avatar-actions button, .upload { display: inline-block; margin-top: .8rem; padding: .7rem .9rem; border: 1px solid rgba(150,190,255,.25); border-radius: 8px; color: #fff; background: #285a9d; cursor: pointer; }
  .avatar-actions { display: flex; gap: .7rem; flex-wrap: wrap; }
  .upload input { display: none; }
  .hint { color: #8292a8; font-size: .85rem; }
  .error { color: #ff9999; }
  .notice { color: #9ee7b0; }
</style>

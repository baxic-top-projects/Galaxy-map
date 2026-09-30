<script>
  import { promoteAdmin } from '../lib/auth/authApi.js'

  let { locale = 'ru', onBack = undefined } = $props()
  let email = $state('')
  let busy = $state(false)
  let error = $state('')
  let notice = $state('')

  async function promote() {
    if (!window.confirm(locale === 'en' ? `Make ${email} an administrator?` : `Назначить ${email} администратором?`)) return
    busy = true
    error = ''
    notice = ''
    try {
      const result = await promoteAdmin(email)
      notice = locale === 'en'
        ? `${result?.email || email} is now an administrator.`
        : `${result?.email || email} теперь администратор.`
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
    }
  }
</script>

<main class="page">
  <section class="card">
    <button class="back" type="button" onclick={() => onBack?.()}>← {locale === 'en' ? 'Back' : 'Назад'}</button>
    <h1>{locale === 'en' ? 'Role management' : 'Управление ролями'}</h1>
    <p>{locale === 'en' ? 'Enter the exact email of an existing user.' : 'Введите точный email существующего пользователя.'}</p>
    <form onsubmit={(event) => { event.preventDefault(); promote() }}>
      <input bind:value={email} required type="email" autocomplete="off" placeholder="user@example.com" />
      <button disabled={busy} type="submit">
        {busy
          ? (locale === 'en' ? 'Saving…' : 'Сохранение…')
          : (locale === 'en' ? 'Make administrator' : 'Назначить администратором')}
      </button>
    </form>
    {#if error}<p class="error">{error}</p>{/if}
    {#if notice}<p class="notice">{notice}</p>{/if}
  </section>
</main>

<style>
  .page { min-height: 100vh; display: grid; place-items: center; padding: 1rem; background: #05070f; }
  .card { width: min(520px, 100%); padding: 1.6rem; border-radius: 16px; border: 1px solid rgba(150,190,255,.2); background: #09111f; }
  .back { border: 0; background: transparent; color: #aac9f2; cursor: pointer; }
  form { display: flex; gap: .7rem; margin-top: 1.2rem; }
  input { flex: 1; min-width: 0; padding: .75rem; border: 1px solid rgba(150,190,255,.25); border-radius: 8px; color: #fff; background: #101a2b; }
  form button { padding: .75rem 1rem; border: 0; border-radius: 8px; color: #fff; background: #8d5227; cursor: pointer; }
  .error { color: #ff9999; }
  .notice { color: #9ee7b0; }
</style>

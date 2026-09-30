<script>
  import {
    forgotPassword,
    googleLoginUrl,
    login,
    registerAccount,
    resetPassword,
    verifyEmail,
  } from '../lib/auth/authApi.js'

  let {
    mode = 'login',
    locale = 'ru',
    onAuthenticated = undefined,
    onNavigate = undefined,
  } = $props()

  let email = $state('')
  let password = $state('')
  let displayName = $state('')
  let busy = $state(false)
  let error = $state('')
  let notice = $state('')

  async function submit() {
    busy = true
    error = ''
    notice = ''
    try {
      if (mode === 'login') {
        onAuthenticated?.(await login(email, password))
      } else if (mode === 'register') {
        await registerAccount({ email, password, display_name: displayName })
        notice = locale === 'en' ? 'Check your email to verify the account.' : 'Проверьте почту для подтверждения аккаунта.'
      } else if (mode === 'forgot') {
        await forgotPassword(email)
        notice = locale === 'en' ? 'Password reset email sent.' : 'Письмо для сброса пароля отправлено.'
      } else if (mode === 'reset') {
        const token = new URLSearchParams(window.location.search).get('token') || ''
        await resetPassword(token, password)
        notice = locale === 'en' ? 'Password changed. You can sign in.' : 'Пароль изменён. Теперь можно войти.'
      } else if (mode === 'verify') {
        const token = new URLSearchParams(window.location.search).get('token') || ''
        await verifyEmail(token)
        notice = locale === 'en' ? 'Email verified.' : 'Email подтверждён.'
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
    }
  }

  $effect(() => {
    if ((mode === 'verify') && !busy && !notice && !error) submit()
  })
</script>

<main class="page">
  <section class="card">
    <button class="back" type="button" onclick={() => onNavigate?.('/')}>← {locale === 'en' ? 'Map' : 'К карте'}</button>
    <h1>
      {mode === 'register'
        ? (locale === 'en' ? 'Create account' : 'Регистрация')
        : mode === 'forgot'
          ? (locale === 'en' ? 'Password recovery' : 'Восстановление пароля')
          : mode === 'reset'
            ? (locale === 'en' ? 'New password' : 'Новый пароль')
            : mode === 'verify'
              ? (locale === 'en' ? 'Email verification' : 'Подтверждение email')
              : (locale === 'en' ? 'Sign in' : 'Вход')}
    </h1>

    {#if mode !== 'verify'}
      <form onsubmit={(event) => { event.preventDefault(); submit() }}>
        {#if mode === 'register'}
          <label>
            <span>{locale === 'en' ? 'Display name' : 'Имя'}</span>
            <input bind:value={displayName} required minlength="2" autocomplete="name" />
          </label>
        {/if}
        {#if mode !== 'reset'}
          <label>
            <span>Email</span>
            <input bind:value={email} required type="email" autocomplete="email" />
          </label>
        {/if}
        {#if mode === 'login' || mode === 'register' || mode === 'reset'}
          <label>
            <span>{locale === 'en' ? 'Password' : 'Пароль'}</span>
            <input bind:value={password} required minlength={mode === 'login' ? 1 : 12} type="password" autocomplete={mode === 'login' ? 'current-password' : 'new-password'} />
          </label>
        {/if}
        <button class="primary" disabled={busy} type="submit">
          {busy ? (locale === 'en' ? 'Please wait…' : 'Подождите…') : (locale === 'en' ? 'Continue' : 'Продолжить')}
        </button>
      </form>
    {/if}

    {#if mode === 'login'}
      <button class="google" type="button" onclick={() => (window.location.href = googleLoginUrl())}>
        {locale === 'en' ? 'Continue with Google' : 'Войти через Google'}
      </button>
      <nav>
        <button type="button" onclick={() => onNavigate?.('/register')}>{locale === 'en' ? 'Create account' : 'Регистрация'}</button>
        <button type="button" onclick={() => onNavigate?.('/forgot-password')}>{locale === 'en' ? 'Forgot password?' : 'Забыли пароль?'}</button>
      </nav>
    {/if}
    {#if mode === 'register' || mode === 'forgot'}
      <button class="link" type="button" onclick={() => onNavigate?.('/login')}>{locale === 'en' ? 'Back to sign in' : 'Вернуться ко входу'}</button>
    {/if}
    {#if error}<p class="error">{error}</p>{/if}
    {#if notice}<p class="notice">{notice}</p>{/if}
  </section>
</main>

<style>
  .page { min-height: 100vh; display: grid; place-items: center; background: radial-gradient(circle at 50% 20%, #172a4a, #05070f 65%); padding: 1rem; box-sizing: border-box; }
  .card { width: min(420px, 100%); padding: 1.5rem; border: 1px solid rgba(150,190,255,.2); border-radius: 16px; background: rgba(7,12,24,.96); box-shadow: 0 20px 60px rgba(0,0,0,.45); }
  h1 { margin: .7rem 0 1.4rem; }
  form, label { display: grid; gap: .45rem; }
  form { gap: 1rem; }
  input { padding: .75rem; color: #fff; border: 1px solid rgba(150,190,255,.25); border-radius: 8px; background: #0d1728; }
  button { cursor: pointer; }
  .primary, .google { width: 100%; padding: .75rem; border-radius: 8px; border: 1px solid rgba(150,190,255,.28); color: #fff; background: #285a9d; }
  .google { margin-top: .8rem; background: #17243a; }
  .back, .link, nav button { border: 0; color: #a9c8f4; background: transparent; }
  nav { margin-top: 1rem; display: flex; justify-content: space-between; }
  .link { margin-top: 1rem; }
  .error { color: #ff9999; }
  .notice { color: #9ee7b0; }
</style>

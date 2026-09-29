import { mount } from 'svelte'
import App from './App.svelte'

const preview = document.querySelector('.site-preview')
const app = mount(App, {
  target: document.getElementById('app'),
})
preview?.remove()

export default app

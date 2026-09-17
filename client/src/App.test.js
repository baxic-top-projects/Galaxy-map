import { fireEvent, render, screen } from '@testing-library/svelte'
import { describe, expect, test } from 'vitest'

import App from './App.svelte'

describe('App', () => {
  test('increments the displayed count for each user click', async () => {
    render(App)
    const counter = screen.getByRole('button', { name: 'count is 0' })

    await fireEvent.click(counter)
    await fireEvent.click(counter)

    expect(screen.getByRole('button', { name: 'count is 2' })).toBe(counter)
  })
})

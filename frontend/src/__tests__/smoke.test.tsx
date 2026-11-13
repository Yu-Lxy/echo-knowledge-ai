import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../App'

describe('M0 冒烟测试', () => {
  it('渲染应用标题', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Echo Knowledge AI' })).toBeInTheDocument()
  })
})

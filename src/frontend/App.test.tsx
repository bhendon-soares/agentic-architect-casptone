import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import * as mockRuns from './mockRuns'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('accepts the demo input, executes the mock run and displays its sourced result', async () => {
  const start = vi.spyOn(mockRuns, 'startRun')
  const status = vi.spyOn(mockRuns, 'getRunStatus')
  render(<App />)

  const input = screen.getByRole('textbox', { name: 'Descreva seu problema' }) as HTMLTextAreaElement
  const submitted = input.value
  expect(submitted).toContain('Esqueci a senha')
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))

  expect(screen.getByText('Atendimento: em andamento')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Reiniciar' }).hasAttribute('disabled')).toBe(true)
  expect(screen.getByRole('button', { name: 'Em andamento…' }).hasAttribute('disabled')).toBe(true)
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getByText(submitted)).toBeTruthy()

  expect(await screen.findByText('Atendimento: concluído', {}, { timeout: 3000 })).toBeTruthy()
  expect(start).toHaveBeenCalledWith({ message_text: submitted })
  expect(status).toHaveBeenCalledOnce()
  expect(screen.getByText('Redefinição de senha')).toBeTruthy()
  expect(screen.getByText('knowledge/password_reset.md')).toBeTruthy()
  expect(screen.getByText(/Use o fluxo oficial de redefinição de senha/)).toBeTruthy()
})
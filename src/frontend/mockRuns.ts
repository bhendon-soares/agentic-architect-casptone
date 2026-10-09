export type RunInput = { message_text: string }
export type RunStatus = 'idle' | 'running' | 'done'
export type FinalAction = 'respond' | 'ask_clarification' | 'open_ticket' | 'blocked'
export type RunError = { code: string; message: string; retryable: boolean }
export type RunResult = {
  final_action: FinalAction
  message_pt_br: string
  summary: string
  sources: { title: string; path: string; snippet: string }[]
}
export type RunSnapshot = { status: 'running' } | { status: 'done'; result: RunResult }

const runs = new Map<string, RunInput>()

const pause = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds))

export async function startRun(input: RunInput): Promise<string> {
  await pause(350)
  const runId = crypto.randomUUID()
  runs.set(runId, { ...input })
  return runId
}

export async function getRunStatus(runId: string): Promise<RunSnapshot> {
  await pause(1100)
  if (!runs.has(runId)) {
    throw { code: 'RUN_NOT_FOUND', message: 'Atendimento indisponível. Tente novamente.', retryable: true } satisfies RunError
  }
  return {
    status: 'done',
    result: {
      final_action: 'respond',
      summary: 'Orientação de redefinição de senha disponível na fonte local.',
      message_pt_br: 'Para qual conta corporativa de demonstração você precisa redefinir a senha? Não informe a senha atual aqui. Use o fluxo oficial de redefinição de senha da organização e a verificação de identidade configurada nesse fluxo. Se não conseguir acessar o método de verificação, o suporte deve abrir um incidente para validação manual. Nenhuma senha temporária será enviada por este chat.',
      sources: [{
        title: 'Redefinição de senha',
        path: 'knowledge/password_reset.md',
        snippet: 'Confirme com o solicitante qual conta corporativa apresenta o problema, sem solicitar nem registrar a senha atual. Oriente o uso do fluxo oficial de redefinicao de senha da organizacao e da verificacao de identidade configurada nesse fluxo. Se o acesso ao metodo de verificacao estiver indisponivel, abra um incidente para validacao manual pelo suporte; nao envie senha temporaria pelo chat.',
      }],
    },
  }
}
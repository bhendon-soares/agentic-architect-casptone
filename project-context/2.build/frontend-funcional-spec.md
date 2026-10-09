# Especificacao funcional do frontend: chat de suporte (primeira etapa)

## Inputs

- Entrada de demonstracao ficticia em pt-BR: "Esqueci a senha da minha conta corporativa de demonstração. Consigo acessar o método oficial de verificação de identidade."
- A mensagem e obrigatoria e nao pode ser vazia. Nao solicitar senha, token, credenciais nem dados pessoais de terceiros.
- Modo de demonstracao identificado na interface; sem sessao real ou persistencia nesta etapa.

## Run

- Uma rota de chat: descrever problema, Executar atendimento e receber orientacao com fonte no mesmo historico.
- FSM local: `idle -> running -> done`; status visivel no topo com horario da ultima atualizacao, indicador cinza/azul/verde e texto acessivel.
- `startRun(input)` e `getRunStatus(runId)` em `src/frontend/mockRuns.ts` sao abstracoes locais com mocks fixos (350 ms + 1100 ms), nao endpoints adicionais do SAD.
- Durante `running`, bloquear envio duplicado e Reiniciar; exibir progresso em texto alem do indicador visual.
- Falha tecnica: indicador vermelho e mensagem inline; retornar a `idle`, preservar exatamente a entrada e oferecer Tentar novamente com os mesmos dados, mesmo se o campo tiver sido editado depois. O mock de demonstracao nao injeta falha; o tratamento vale para rejeicao de servico. `blocked` e resultado de negocio, nao falha tecnica.

## Results

- Nesta etapa, somente `final_action=respond`: orientacao em pt-BR baseada exclusivamente em `knowledge/password_reset.md`, sem links ou senhas temporarias inventadas.
- Exibir titulo, caminho e trecho da fonte, mais resumo curto do resultado; nao exibir raciocinio interno dos agentes.
- `respond`, `ask_clarification`, `open_ticket` e `blocked` sao acoes finais de negocio, distintas do status da execucao; as tres ultimas nao sao demonstradas nesta etapa.

## History

- Mostrar entrada e resposta no mesmo historico da conversa durante a sessao em memoria; Reiniciar limpa o historico apos a execucao.
- Persistencia de conversa e console admin pertencem ao P0 completo, nao a esta implementacao de frontend mockado.

## Contracts

- Contrato local implementado: `RunInput { message_text: string }`; `RunStatus = 'idle' | 'running' | 'done'`; `FinalAction = 'respond' | 'ask_clarification' | 'open_ticket' | 'blocked'`; `RunSnapshot` e a uniao de `running` e `done` com resultado.
- `RunResult { final_action: FinalAction; message_pt_br: string; summary: string; sources: { title: string; path: string; snippet: string }[] }`; `RunError { code: string; message: string; retryable: boolean }`. A falha acompanha a FSM e nao cria um quarto estado.
- Integracao futura por `@integration.eng`: `POST /api/chat/sessions` cria sessao, `POST /api/chat/sessions/{session_id}/messages` envia mensagem e `GET /api/agent-runs/{agent_run_id}` consulta execucao, seguindo o envelope `{ data, error, meta }` do SAD. Definir o mapeamento de payload com o backend antes de remover os mocks; a autoridade sobre `final_action` permanece no backend.

## Acceptance Criteria

- Entrada ficticia aceita, mocks chamados, `running` e depois `done`, resposta e fonte visiveis no historico.
- Envio duplicado e Reiniciar desabilitados durante execucao; teclado, labels, semantica e layout responsivo.
- Erro tecnico recuperavel preserva a entrada e permite retry com os mesmos dados.
- Tipos, testes e build passam; capturas de entrada, execucao e resultado disponiveis apos a UI existir.

## Spec Sync

| Item | Status | Nota |
| :-- | :-- | :-- |
| Contratos locais vs. PRD/SAD/SFS | Implementado | `src/frontend/mockRuns.ts` e UI; mocks locais nao introduzem endpoints; somente `respond`. |
| Scaffold de `@project.mgr` | Resolvido | Setup documentado e Vite em funcionamento. |
| UI, FSM, mocks e retry | Implementado | Retry preserva a entrada; falha mockada nao e injetada nesta etapa. |
| Teste, typecheck e build | Validado | Um teste do fluxo feliz passou; tipo e build conferidos. |
| Screenshots | Parcial | Entrada, execucao e resultado capturados na sessao; PNGs do navegador nao acessiveis no workspace. |
| Console admin e persistencia P0 | Pendente | Fora da primeira etapa; nao implementados. |
| Gate AAMAD Build | Pendente | `aamad validate --phase build` exige artefatos backend, integration e qa de outras personas. |

## Capturas

- O navegador integrado exibiu capturas de entrada, execucao e resultado na sessao; em andamento ambos os controles estavam desabilitados. A ferramenta de captura grava em um filesystem isolado e nao entregou os PNG no repositorio.
- Para capturar localmente: iniciar `npm run dev` em `src/frontend/`; abrir a URL anunciada; capturar a entrada; clicar em Executar e capturar durante os 1,45 s do mock; capturar o resultado apos a fonte aparecer.

## Sources

- `AGENTS.md`; `aamad.config.yml`; `.github/instructions/aamad-core.instructions.md`; `.github/instructions/development-workflow.instructions.md`; `.github/agents/frontend-eng.agent.md`; `.github/agents/project-mgr.agent.md`.
- `project-context/1.define/prd.md` (FR-001, FR-003, FR-004); `project-context/1.define/sad.md` (frontend e API); `project-context/1.define/sfs/multi-agent-support-flow.md`; `knowledge/password_reset.md`; solicitacao do operador em 2026-10-09.

## Assumptions

- O modo mock usa somente dados ficticios; a resposta de redefinicao de senha nao implica acesso a servicos reais.
- O runtime configurado e `crewai`, sem participacao nesta etapa frontend.

## Open Questions

- Qual sera a forma exata dos payloads dos endpoints do SAD? Alinhar com `@backend.eng`/`@integration.eng` antes da integracao.
- Os payloads de integracao devem ser validados pelo backend antes da troca dos mocks; nao ha outro bloqueio para esta etapa.

## Audit

- Data: 2026-10-09. Persona: `frontend-eng`. Acao: `document-frontend` (especificacao e bloqueio de pre-requisito).
- Ferramentas: leitura de artefatos e regras AAMAD, inspecao do diretorio Build e do scaffold; edicao via `apply_patch`. Modelo e parametros de runtime de agentes: nao aplicaveis a esta etapa, sem execucao de agentes. Prompt Trace omitido: sem geracao de output de alto risco ou producao.
- Revisao em 2026-10-09: scaffold recebido; acao `develop-fe` com mocks, UI, teste e validacao no navegador; especificacao e checklist sincronizados. Sem chamada ao runtime `crewai` e sem output de producao.
- Gates: `corepack npm test`, `corepack npm run typecheck` e `corepack npm run build` aprovados; `.venv/bin/aamad validate --phase build` falhou por artefatos de outras personas (`backend.md`, `integration.md`, `qa.md`; `evals.md` recomendado).
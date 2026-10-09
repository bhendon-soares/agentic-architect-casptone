# Frontend Build: primeira etapa do chat de suporte

## Decisoes

- A primeira etapa e uma unica rota React/TypeScript/Vite em pt-BR, tema escuro e visual minimo, com demonstracao local de `respond` para `password_reset`.
- A resposta deve seguir o procedimento de `knowledge/password_reset.md`: confirmar qual conta apresenta o problema sem pedir senha atual, orientar fluxo oficial e verificacao de identidade; se verificacao indisponivel, encaminhar a suporte para validacao manual; nao enviar senha temporaria.
- `startRun` e `getRunStatus` em `src/frontend/mockRuns.ts` sao servicos mockados locais com atrasos fixos de 350 ms e 1100 ms. A FSM local e `idle -> running -> done`; erro tecnico retorna a `idle` com entrada preservada e retry identico. As quatro `final_action` sao decisoes de negocio e nao estados de execucao; somente `respond` e demonstrado.
- Sem backend, CrewAI, banco, ServiceNow real ou alteracoes no PRD/SAD nesta etapa. Console admin e persistencia sao pendencias do P0 completo, nao funcionalidades entregues.
- A integracao futura substitui os mocks pelas rotas de sessao, mensagem e consulta de execucao previstas no SAD, mantendo o backend como autoridade de `final_action`.

## Spec Sync

| Item | Status | Nota |
| :-- | :-- | :-- |
| Especificacao funcional e contratos | Atualizado | Ver `project-context/2.build/frontend-funcional-spec.md`; contrato local implementado, payload HTTP ainda a alinhar. |
| Scaffold React/TypeScript/Vite e setup | Resolvido | `project-context/2.build/setup.md` entregue; typecheck e build do scaffold aprovados. |
| Implementacao e testes do chat | Validado | React/FSM/mocks e um teste do fluxo feliz com fonte. Falha tecnica tratada, sem injecao de falhas. |
| README e comandos | Atualizado | Passos locais e handoff de integracao registrados na raiz. |
| Screenshots | Parcial | Entrada/execucao/resultado visiveis na sessao; arquivos isolados pelo navegador; roteiro na especificacao. |
| Console admin e persistencia | Pendente | P0 completo; nao realizados por esta fatia mockada. |
| Gate AAMAD Build | Pendente | Faltam artifacts de backend, integration e qa de outras personas. |

## Validacao e handoff

- `corepack npm test`: um teste aprovado, exercitando entrada, mocks, `running`, `done`, resposta e fonte. `corepack npm run typecheck` e `corepack npm run build` sao os gates de codigo.
- Navegador: status em andamento e controles desabilitados observados; duas mensagens e fonte visivel apos conclusao; largura movel verificada sem overflow horizontal.
- `@integration.eng` substituira o servico local pelos endpoints do SAD, sem transferir ao frontend a autoridade sobre `final_action`. A restricao do runtime `crewai` nao aparece nesta UI mockada; sem streaming prometido.
- Console admin, persistencia e validacao Build completa continuam pendentes das demais personas.

## Sources

- `AGENTS.md`; `aamad.config.yml`; `.github/instructions/aamad-core.instructions.md`; `.github/instructions/development-workflow.instructions.md`; `.github/agents/frontend-eng.agent.md`; `.github/agents/project-mgr.agent.md`.
- `project-context/1.define/prd.md`; `project-context/1.define/sad.md`; `project-context/1.define/sfs/multi-agent-support-flow.md`; `knowledge/password_reset.md`; `project-context/2.build/frontend-funcional-spec.md`.

## Assumptions

- Mocks e textos usarao somente dados ficticios de demonstracao. `crewai` e runtime do backend futuro, nao do frontend.

## Open Questions

- Quais payloads concretos da API serao acordados por backend e integracao para substituir os mocks?

## Audit

- Data: 2026-10-09. Persona: `frontend-eng`. Acao: `document-frontend` e `halt-and-report` por ausencia de pre-requisito.
- Ferramentas: leitura de regras e artefatos, inspecao da arvore Build e edicao via `apply_patch`. Modelo/temperatura/max_tokens de runtime: nao aplicaveis, pois nenhum agente do produto foi executado. Prompt Trace omitido: nao houve output de alto risco ou de producao.
- Revisao em 2026-10-09: handoff recebido; acao `develop-fe`, teste automatizado, build e verificacao visual. Teste e ferramentas de navegador registrados acima; sem execucao de agentes do produto.
- Revisao do gate: `corepack npm test`, `corepack npm run typecheck`, `corepack npm run build` aprovados; `.venv/bin/aamad validate --phase build` falhou por `backend.md`, `integration.md`, `qa.md` ausentes; `evals.md` recomendado antes de Deliver. Capturas dos tres estados ficaram visiveis na sessao, nao no repositorio.
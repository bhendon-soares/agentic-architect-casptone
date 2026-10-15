# Integracao do chat P0

## Contrato e implementacao

- `src/frontend/chatApi.ts` consome o envelope `{data,error,meta}` da API. `POST /api/chat/sessions` cria uma sessao no primeiro envio ou ao clicar Reiniciar; `POST /api/chat/sessions/{session_id}/messages` retorna o turno sincrono e a UI exibe `summary`, `message_pt_br`, `sources` e o numero de ticket quando houver. `blocked` e `ask_clarification` sao resultados de negocio, nao erros.
- O frontend salva somente os IDs das sessoes em `localStorage`; ao abrir uma conversa, consulta `GET /api/chat/sessions/{session_id}` para recuperar mensagens e turnos persistidos. A lista so inclui sessoes criadas neste navegador: nao existe endpoint P0 de listagem geral de sessoes. Reiniciar preserva as sessoes anteriores no backend e na lista local.
- Vite encaminha `/api` para `127.0.0.1:8000` em desenvolvimento; em producao o servidor da UI precisa encaminhar `/api` ao backend sob a mesma origem. A API nao usa streaming nem polling para completar a mensagem; `GET /api/agent-runs/{id}` continua reservado para consulta administrativa/reconciliacao.
- Cada novo envio gera uma `Idempotency-Key`. Tentar novamente usa exatamente o mesmo texto e a mesma chave, mesmo se o campo for editado. Para `TICKET_CREATE_FAILED` e `TICKET_OUTCOME_UNKNOWN` o botao permanece por decisao do operador, mas so repete a chave local: nao cria outro incidente na PDI. A UI recomenda consultar o suporte antes de pedir outro incidente. Um novo envio com chave nova apos falha incerta nao e uma reconciliacao segura; depende de decisao humana.

## Verificacao

- `corepack npm test`: quatro testes de contrato UI/HTTP simulado, cobrindo criacao/envio, troca e recarga de sessoes e retry idempotente apos resultado incerto.
- `corepack npm run typecheck` e `corepack npm run build`: aprovados. Estes testes nao executam o runtime CrewAI real nem a PDI.
- Smoke HTTP pelo proxy Vite com backend/PostgreSQL ativos: POST sessao 201, POST mensagem ficticia bloqueada 200 (`final_action=blocked`), GET historico com duas mensagens e um turno. Este caminho bloqueia antes de CrewAI e ServiceNow; nao valida inferencia real nem ticket PDI.
- Inspecao no navegador: envio bloqueado concluido, Reiniciar criou nova sessao, seletor restaurou a conversa anterior. Fluxo de `respond` com provider real nao foi exercitado aqui.
- `.venv/bin/aamad validate --phase build` (na raiz) ainda falha: `backend.md` ausente (aviso), `qa.md` ausente (erro) e `evals.md` recomendado (aviso). Nenhuma pendencia foi apontada neste artefato de integracao.

## Sources

- `project-context/1.define/prd.md`, `project-context/1.define/sad.md`, `project-context/1.define/sfs/multi-agent-support-flow.md`, `project-context/2.build/backend-funcional-spec.md`, `project-context/2.build/frontend-funcional-spec.md`, `src/backend/app/main.py`, `src/frontend/App.tsx`, `src/frontend/chatApi.ts` e decisoes do operador nesta conversa (2026-10-15).

## Assumptions

- Runtime selecionado: `crewai` em `aamad.config.yml`. API no host local na porta 8000; dados da demo sao ficticios. O backend permanece autoridade de `final_action` e da persistencia. Sem autenticacao: somente demo local controlada.

## Open Questions

- `MINIMUM_TICKET_DATA_MISSING` apos a unica pergunta continua sem aprovacao de produto e nao faz parte do contrato implementado. Nao declarar aceite desse ramo ate a decisao.
- Sessao acessivel em outro navegador/dispositivo exigiria listagem/autenticacao de sessoes, fora do contrato P0. Janela de timeout HTTP e reconciliacao de incidentes incertos requerem acordo com backend/seguranca.
- A chave da tentativa pendente permanece somente na memoria da aba; recarregar durante erro incerto perde o retry correlacionado. Consultar suporte/registro local antes de iniciar novo envio nessa situacao.

## Audit

- 2026-10-15; persona `integration-eng`; acoes `*integrate-api`, `*verify-messageflow`, `*log-integration`. Runtime resolvido: `AAMAD_TARGET_RUNTIME=crewai` pela configuracao do projeto (sem override informado). Ferramentas: leitura de contrato/codigo, `apply_patch`, npm test/typecheck/build, HTTP local e navegador integrado; modelo/temperatura/max_tokens/rate do runtime de agentes nao foram alterados. Prompt Trace omitido: smoke com bloqueio deterministico, sem prompts de producao ou geracao de respostas pelo runtime. Validacao humana e de seguranca ainda pendentes.
# Setup: scaffold do frontend MVP

## Escopo

- Scaffold minimo React/TypeScript/Vite para a primeira etapa do chat em pt-BR. A pagina inicial e apenas um marcador tecnico; nao implementa chat, estados, mocks nem regras de negocio.
- O runtime `crewai` e a linguagem primaria Python da configuracao dizem respeito ao backend futuro. Nao foram adicionados backend, banco, ServiceNow, testes de aplicacao ou variaveis de ambiente sem uso neste scaffold.
- O P0 completo do PRD/SAD inclui outras entregas. Este setup nao conclui a fase Build nem os criterios de aceite do frontend funcional.

## Estrutura

| Caminho | Finalidade |
| :-- | :-- |
| `src/frontend/package.json`, `src/frontend/package-lock.json` | Scripts, dependencias e versoes travadas pelo npm. |
| `src/frontend/index.html` | Entrada HTML em pt-BR. |
| `src/frontend/vite.config.ts`, `src/frontend/tsconfig.json` | Configuracao Vite/React e checagem TypeScript estrita. |
| `src/frontend/main.tsx`, `src/frontend/App.tsx` | Caminhos atuais da montagem React e do chat; o marcador tecnico deste scaffold foi substituido por `@frontend.eng`. |

## Dependencias e ambiente

- Requer Node.js compativel com Vite 7 (>=20.19 ou >=22.12); verificado com Node 22.22.1 no Linux/WSL e npm 11.12.1 via Corepack.
- Versoes instaladas em `src/frontend/package-lock.json`: `react` 19.3.0, `react-dom` 19.3.0, `@types/react` 19.3.0, `@types/react-dom` 19.3.0, `@vitejs/plugin-react` 5.2.0, `typescript` 5.9.3 e `vite` 7.3.7. Sem biblioteca de UI, cliente HTTP ou dependencia de backend neste marco.
- Atualmente, executar `npm ci`, `npm run dev`, `npm run typecheck`, `npm run build` e `npm run preview` em `src/frontend/`. O servidor de desenvolvimento anuncia sua URL local ao iniciar. `dist/` e `node_modules/` sao ignorados pelo Git.
- Neste WSL, `npm` no PATH aponta para o Windows e falha ao instalar `esbuild` a partir de caminho UNC. Usar `corepack prepare npm@11.12.1 --activate` e substituir `npm` por `corepack npm` nos comandos acima. Em um ambiente com npm Linux nativo, usar `npm` normalmente.

## Verificacoes

- `corepack npm install`: concluido; auditoria da instalacao informou 0 vulnerabilidades.
- `corepack npm run typecheck`: aprovado.
- `corepack npm run build`: aprovado; `vite build` gerou `dist/`.
- `corepack npm run dev -- --host 127.0.0.1`: servidor Vite iniciado em `http://127.0.0.1:5173/` nesta sessao.
- `.venv/bin/aamad validate --phase build`: falhou conforme esperado; faltam `backend.md`, `integration.md` e `qa.md`, e `evals.md` e recomendado antes de Deliver.
- Ainda nao ha testes funcionais, UI de chat, capturas de tela nem validacao Build completa. Essas verificacoes dependem das respectivas implementacoes e artefatos das demais personas.

## Handoff

- Scaffold pronto para encaminhamento a `@frontend.eng`: implementar a primeira etapa descrita em `project-context/2.build/frontend-funcional-spec.md` e `project-context/2.build/frontend.md`, substituindo o marcador tecnico. Nenhuma chamada a essa persona foi executada neste registro.
- Nao marcar Build como concluida apenas por este setup; backend, integracao, QA e demais entregas seguem pendentes.

## Sources

- `AGENTS.md`; `aamad.config.yml`; `.github/agents/project-mgr.agent.md`; `.github/instructions/aamad-core.instructions.md`.
- `project-context/1.define/prd.md` (Infrastructure Specifications); `project-context/1.define/sad.md` (Frontend Architecture Specification e CI/CD); `project-context/2.build/frontend-funcional-spec.md`; `project-context/2.build/frontend.md`.

## Assumptions

- npm e a ferramenta de pacotes deste scaffold; o lockfile fixa as versoes transitivas. O placeholder nao representa a interface final do MVP.
- A configuracao de tema escuro e visual minimo sera aplicada pela implementacao de `@frontend.eng`, nao pelo scaffold.

## Open Questions

- Os payloads finais da API e sua integracao com o backend permanecem para `@backend.eng` e `@integration.eng`.
- A persona `@project.mgr` nao estava disponivel para invocacao nesta sessao; o handoff formal entre personas ainda precisa ocorrer no fluxo AAMAD.

## Audit

- Data: 2026-10-09. Persona solicitada: `@project.mgr`; execucao: assistente GitHub Copilot apos falha de invocacao da persona (`Requested agent '@project.mgr' not found`). Acoes: scaffold frontend, instalacao, verificacao e documentacao de setup.
- Ferramentas: leitura de arquivos e regras, `apply_patch`, terminal para Corepack/npm/typecheck/build. Runtime de aplicacao selecionado em `aamad.config.yml`: `crewai`, nao executado neste setup. Modelo, temperatura e max_tokens de agentes do produto: nao aplicaveis, pois nenhum agente do produto foi executado. Prompt Trace omitido: nenhum output de alto risco ou producao foi gerado.
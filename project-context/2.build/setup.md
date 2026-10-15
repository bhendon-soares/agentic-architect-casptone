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

## Scaffold backend P0 (2026-10-13)

- O frontend e seu registro acima foram preservados. Este marco adiciona somente a estrutura do backend; nao implementa endpoints P0, schemas de negocio, tabelas, agentes, prompts, tarefas ou adapters funcionais.
- Estrutura: `src/backend/app/main.py` e a entrada ASGI FastAPI sem rotas de produto; `app/schemas/`, `app/persistence/`, `app/knowledge/` e `app/adapters/` reservam os respectivos modulos; `app/runtime/crew.py` localiza `config/agents.yaml` e `config/tasks.yaml` (ambos `{}`), com `Process.sequential`, `allow_delegation=false`, `memory=False` e limite de iteracoes 12 como defaults, sem criar crew. `tests/test_scaffold.py` cobre somente o scaffold. `migrations/` e `alembic.ini` preparam o Alembic sem metadata ou revisoes.
- `src/backend/pyproject.toml` declara Python >=3.11,<3.14, FastAPI, Uvicorn, CrewAI, Pydantic, SQLAlchemy, Psycopg e Alembic; pytest e Ruff sao dependencias de desenvolvimento. O pacote foi instalado no `.venv` existente via ferramenta de instalacao Python e reinstalado em modo editavel. Versoes diretas instaladas: `crewai` 1.15.27, `fastapi` 0.143.0, `uvicorn` 0.54.0, `pydantic` 2.12.5, `sqlalchemy` 2.1.4, `psycopg`/`psycopg-binary` 3.3.6, `alembic` 1.20.0, `pytest` 9.1.1, `ruff` 0.17.0. O manifesto usa intervalos compativeis e nao e lockfile; dependencias transitivas do CrewAI nao habilitam vector DB no aplicativo.
- Pre-requisitos: Python 3.11-3.13, `uv` (ou `pip` para instalar o extra `.[dev]`) e Docker Compose com integracao WSL habilitada para PostgreSQL 16. O `.env.example` na raiz usa somente placeholders; copie-o para `.env`, escolha uma senha local e mantenha `POSTGRES_PASSWORD` igual a senha em `DATABASE_URL` (codifique caracteres especiais na URL). Nao versionar `.env`. Os comandos abaixo assumem a raiz do repositorio, exceto onde indicado.
- Instalar: `uv venv .venv` se ainda nao existir; `uv pip install --python .venv/bin/python -e './src/backend[dev]'`. Banco: `docker compose --env-file .env up -d db` e `docker compose --env-file .env down` para parar. API vazia, a partir de `src/backend/`: `../../.venv/bin/python -m uvicorn app.main:app --env-file ../../.env --reload`. Ainda nao ha endpoints funcionais; FastAPI expoe apenas sua documentacao automatica.
- Migrations, a partir de `src/backend/`: exporte `DATABASE_URL` do `.env` no ambiente local e execute `../../.venv/bin/alembic history`; somente depois de `@backend.eng` criar models/metadata e a primeira revisao devem ser usados `revision --autogenerate` ou `upgrade head`. `KNOWLEDGE_BASE_PATH=../../knowledge` e relativo a execucao a partir de `src/backend/`; os arquivos na raiz `knowledge/` ja existiam e nao foram alterados.
- Verificacoes realizadas: `../../.venv/bin/python -m pytest -q tests` (1 passou) e `../../.venv/bin/ruff check app tests migrations/env.py` (passou), a partir de `src/backend/`; apos instalacao editavel, `.venv/bin/pytest -q src/backend/tests` (1 passou) e Ruff (passou) na raiz; parse TOML dos manifests e YAML do Compose/configuracoes (passou); `../../.venv/bin/alembic history` (passou, sem revisoes); `git diff --check` (passou).
- Docker Compose nao pode ser validado pelo CLI nem o PostgreSQL iniciado neste WSL: `docker` informa que a integracao Docker Desktop com a distro esta desativada. API, conexao com banco, migrations reais, CrewAI e ServiceNow nao foram exercitados. `.venv/bin/aamad validate --phase build` na raiz continua falhando por `qa.md` ausente; `backend.md` e `integration.md` estao pendentes e `evals.md` e recomendado.
- Handoff: `@backend.eng` define contratos Pydantic, schemas/tabelas/revisoes, validacao e redacao, agentes/tasks em YAML, `output_pydantic` e contextos validados, rotas, persistencia e adapters mock/ServiceNow. `@integration.eng` cuida da integracao ponta a ponta, `@qa.eng` dos testes funcionais, e `@security.eng` da avaliacao antes de Deliver. Nao marcar Build concluida neste marco.

## Sources

- `AGENTS.md`; `aamad.config.yml`; `.github/agents/project-mgr.agent.md`; `.github/instructions/aamad-core.instructions.md`.
- `project-context/1.define/prd.md` (Infrastructure Specifications); `project-context/1.define/sad.md` (Frontend Architecture Specification e CI/CD); `project-context/2.build/frontend-funcional-spec.md`; `project-context/2.build/frontend.md`.
- Scaffold backend: `project-context/1.define/prd.md` (Runtime & Agent Specifications, Infrastructure Specifications), `project-context/1.define/sad.md` (Runtime-Conditional Configuration, Backend Architecture, Configuration and `.env` Strategy, Docker/PostgreSQL Local).

## Assumptions

- npm e a ferramenta de pacotes deste scaffold; o lockfile fixa as versoes transitivas. O placeholder nao representa a interface final do MVP.
- A configuracao de tema escuro e visual minimo sera aplicada pela implementacao de `@frontend.eng`, nao pelo scaffold.
- Para o backend, a execucao e feita a partir de `src/backend/`; `.env` e Docker Compose ficam na raiz e compartilham a senha local de PostgreSQL. O manifesto Python nao tem lockfile nesta etapa.

## Open Questions

- Os payloads finais da API e sua integracao com o backend permanecem para `@backend.eng` e `@integration.eng`.
- A persona `@project.mgr` nao estava disponivel para invocacao nesta sessao; o handoff formal entre personas ainda precisa ocorrer no fluxo AAMAD.
- A validacao do Compose pelo Docker CLI e do banco real depende da integracao Docker Desktop nesta distro WSL. A selecao do provedor/modelo LLM e as credenciais ServiceNow reais pertencem a configuracao local posterior, sem valores definidos neste scaffold.

## Audit

- Data: 2026-10-09. Persona solicitada: `@project.mgr`; execucao: assistente GitHub Copilot apos falha de invocacao da persona (`Requested agent '@project.mgr' not found`). Acoes: scaffold frontend, instalacao, verificacao e documentacao de setup.
- Ferramentas: leitura de arquivos e regras, `apply_patch`, terminal para Corepack/npm/typecheck/build. Runtime de aplicacao selecionado em `aamad.config.yml`: `crewai`, nao executado neste setup. Modelo, temperatura e max_tokens de agentes do produto: nao aplicaveis, pois nenhum agente do produto foi executado. Prompt Trace omitido: nenhum output de alto risco ou producao foi gerado.
- Data: 2026-10-13. Persona solicitada: `@project.mgr`; acao: `*setup-project`, `*install-dependencies`, `*configure-env`, `*document-setup` para backend. Ferramentas: leitura de PRD/SAD/config/regras, `apply_patch`, instalacao Python via ferramenta do editor, pytest/Ruff/Alembic/validacao AAMAD via terminal. Runtime resolvido: `crewai` (`aamad.config.yml`, sem override registrado); agentes do produto nao executados. Modelo, temperatura e max_tokens efetivos: nao aplicaveis; controles LLM apenas placeholders no `.env.example`. Prompt Trace omitido: nenhum output de producao ou alto risco foi gerado.
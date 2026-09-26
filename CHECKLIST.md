# AAMAD Execution Checklist

Este checklist guia voce passo a passo na execucao do AAMAD da Phase 1 (Define), passando pela Phase 2 (Build), ate a Phase 3 (Deliver), usando os agentic workflows definidos no framework.  
**Artifacts** (`project-context/`, templates, Phase 1 prompt) sao os mesmos em toda IDE; **onde agents e rules ficam** depende de como voce inicializou AAMAD.

---

## Install and IDE layout

- [ ] Instale prerequisites (Python 3.9+, Node quando sua stack precisar; veja [README.md](README.md)).
- [ ] Instale AAMAD: `pip install aamad` ou `uv pip install aamad`.
- [ ] Inicialize os arquivos do framework para sua IDE (escolha uma):

  | IDE | Command |
  | :-- | :------ |
  | **Cursor** (default) | `aamad init --ide cursor --dest .` |
  | **Claude Code** | `aamad init --ide claude-code --dest .` |
  | **VS Code + GitHub Copilot** | `aamad init --ide vscode --dest .` |

- [ ] Confirme os outputs esperados para a **sua** IDE (templates continuam em `.cursor/templates/` para todas):

  - [ ] **Cursor:** `.cursor/agents/`, `.cursor/rules/`, `.cursor/prompts/`, `.cursor/skills/`, `.cursor/templates/`, root `AGENTS.md`
  - [ ] **Claude Code:** `.claude/` (`agents/`, `rules/`, `commands/`, `skills/`, `settings.json`), `.cursor/templates/`, `AGENTS.md`
  - [ ] **VS Code + Copilot:** `.github/instructions/`, `.github/agents/`, `.github/prompts/` (includes `run-evals.prompt.md`), `.vscode/settings.json`, `.cursor/templates/`, `AGENTS.md`

- [ ] Opcionalmente copie `aamad.config.example.yml` → `aamad.config.yml` e defina project preferences.
- [ ] Leia rapidamente o `AGENTS.md` da raiz para saber onde as personas ficam na sua IDE.
- [ ] Para **invoke personas** (`@product-mgr`, `@backend.eng`, …) e referenciar arquivos, siga [README.md → Using AAMAD in your IDE](README.md#using-aamad-in-your-ide) (Cursor, Claude Code e VS Code diferem).

---

## Runtime target (Phase 2 generated MVP)

- [ ] Defina `AAMAD_TARGET_RUNTIME` antes do Build-phase implementation work (registre o valor resolvido em `sad.md` Audit e outros artifacts conforme as rules exigirem):

  - [ ] `crewai` (default if unset / unknown per adapter registry)
  - [ ] `claude-agent-sdk`
  - [ ] `cursor-sdk`

---

## Phase 1: Requirements Definition (`@product-mgr`)

- [ ] Invoque `@product-mgr` usando o agent chat da sua IDE (veja **Install and IDE layout** e README → Using AAMAD in your IDE).
- [ ] **Recommended for specialized projects:** rode `*elicit-requirements` (ou escreva `system-description.md` voce mesmo) antes de MRD/PRD.
- [ ] **MRD decision:**
  - [ ] Produto commercial / market-facing → produza MRD
  - [ ] Ferramenta internal / personal / operational → pule MRD; registre rationale em PRD Assumptions
- [ ] Rode conforme necessario:
    - [ ] `*elicit-requirements` — System description em project-context/1.define/system-description.md
    - [ ] `*create-mrd` — Market Research Document em project-context/1.define/mrd.md usando .cursor/templates/mrd-template.md
    - [ ] `*create-prd` — Product Requirements Document em project-context/1.define/prd.md usando .cursor/templates/prd-template.md
    - [ ] `*create-context` — MRD (salvo se pulado) e PRD com context summary para handoff
    - [ ] `*create-stories` — MVP user stories em project-context/1.define/user-stories/
- [ ] Valide completude: market analysis (quando MRD for produzido), user personas, feature requirements, acceptance criteria, success metrics e business/operational goals.
- [ ] Registre assumptions e open questions em artifacts para resolucao downstream.
- [ ] Aprove context boundaries e artifacts para technical build phase.

---

## Before Phase 2 Starts

- [ ] Garanta que `project-context/1.define` inclua:
  - [ ] prd.md (PRD) — **required**
  - [ ] mrd.md (MRD) — **optional** (required only for commercial/market-facing projects)
  - [ ] system-description.md — recommended when elicitation was used
  - [ ] sad.md (SAD, after architecture step)
- [ ] Confirme que o framework layout de **Install and IDE layout** ainda esta presente (rode novamente `aamad init` com `--overwrite` apenas se pretende atualizar arquivos gerados).
- [ ] Confirme que `AAMAD_TARGET_RUNTIME` esta definido para o runtime escolhido (veja **Runtime target** acima).
- [ ] Opcionalmente rode `aamad validate --phase define`.

---

## Phase 2: Build Execution

Use o mesmo padrao de invocacao de persona da Phase 1 (Cursor `@name`, Claude Code por subagent name/description, VS Code dropdown ou `@name` — veja README).

### Step 0: Architecture Definition (`@system.arch`)

- [ ] Invoque `@system.arch`.
- [ ] Rode um dos comandos:
  - [ ] `*create-sad` — Gere SAD completo em project-context/1.define/sad.md usando .cursor/templates/sad-template.md.
  - [ ] `*create-sad --mvp` — Gere um SAD MVP enxuto, adiando componentes e NFRs nao essenciais; output para project-context/1.define/sad.md.
- [ ] Valide completude do SAD: stakeholders/concerns, views, quality attributes, decisions, constraints e risks.
- [ ] Registre assumptions e open questions em sad.md para resolucao downstream.
- [ ] Registre `AAMAD_TARGET_RUNTIME` resolvido na secao Audit de sad.md.
- [ ] Rode `*define-eval-criteria` — preencha a evaluation criteria table da section 9 do SAD (dimension, metric, threshold, grading method, source) antes da Build iniciar.

---

### Step 1: Environment Setup (`@project.mgr`)

- [ ] Invoque `@project.mgr`.
- [ ] Run `*setup-project`
  - [ ] Crie scaffold de diretorios e instale required dependencies
  - [ ] Defina environment variables (em .env ou conforme descrito)
  - [ ] Documente todas as acoes em setup.md

---

### Step 2: Frontend Development (`@frontend.eng`)

- [ ] Invoque `@frontend.eng`.
- [ ] Rode `*develop-fe`
  - [ ] Implemente a MVP chat interface (ou UI especificada no PRD)
  - [ ] Adicione UI stubs para planned features futuras
  - [ ] Estilize e torne a interface responsiva
  - [ ] Documente todas as decisions e status em frontend.md

---

### Step 3: Backend Development (`@backend.eng`)

- [ ] Invoque `@backend.eng`.
- [ ] Rode `*develop-be`
  - [ ] Crie scaffold do backend runtime e MVP runtime agent(s) usando o runtime adapter selecionado (`.cursor/rules/adapter-${AAMAD_TARGET_RUNTIME}.mdc` apos init; paths diferem por IDE, mas o conteudo e equivalente)
  - [ ] Adicione stub code para future/backlog agent logic
  - [ ] Implemente backend chat API endpoint
  - [ ] Documente todo o trabalho em backend.md

---

### Step 4: Integration (`@integration.eng`)

- [ ] Invoque `@integration.eng`.
- [ ] Rode `*integrate-api`
  - [ ] Conecte o MVP frontend chat ao backend chat API
  - [ ] Teste basic chat round-trip functionality
  - [ ] Documente integration e known issues em integration.md

---

### Step 5: Quality Assurance (`@qa.eng`)

- [ ] Invoque `@qa.eng`.
- [ ] Rode `*test-unit` — unit tests; mapeie para AC-* IDs quando disponiveis; registre em qa.md
- [ ] Rode `*test-integration` — integration tests atraves de UI/API/runtime; registre em qa.md
- [ ] Rode `*qa` / `*verify-flow`
  - [ ] Execute smoke tests e functional tests no chat flow
  - [ ] Verifique que frontend e backend estao conectados
  - [ ] Registre issues, known gaps e future work em qa.md

---

### Step 5.4: Evaluation Strategy (`@qa.eng`) — recommended before Security/Deliver

- [ ] Rode `*run-evals` seguindo `.cursor/skills/run-evals/SKILL.md`.
- [ ] Implemente a evaluation criteria table da section 9 do SAD quando presente; caso contrario, responda ao operator gap check da skill (thresholds, SLA, risk tolerance, dataset provenance, judge calibration).
- [ ] Construa o golden dataset e graders; cubra accuracy, latency, safety, security e cost.
- [ ] Complete project-context/2.build/evals.md, incluindo Production Monitoring Recommendations para `@devops.eng`.

---

### Step 5.5: Security Assessment (`@security.eng`) — recommended before Deliver

- [ ] Invoque `@security.eng` (obrigatorio quando `aamad.config.yml` define `security.require_security_assessment: true`).
- [ ] Rode `*assess-security` (e `*scan-secrets` / `*review-deps` conforme necessario).
- [ ] Complete project-context/2.build/security.md com findings ordenados por severity.
- [ ] Encaminhe mitigations para as personas responsaveis; nao mude app logic dentro desta persona.

---

### Step 6: Deliver (`@devops.eng`)

- [ ] Invoque `@devops.eng` apos QA artifacts estarem completos (e evals.md / security.md quando disponiveis).
- [ ] Rode `*prepare-release`
  - [ ] Confirme que qa.md documenta MVP verification (pass ou scoped gaps)
  - [ ] Registre status de evals.md e incorpore suas monitoring recommendations na deploy config
  - [ ] Registre status de security.md (presente ou accepted gap)
  - [ ] Resuma release scope e version em deploy.md
- [ ] Rode `*define-deploy` e `*configure-cicd`
  - [ ] Adicione deploy minimo e CI config alinhados ao SAD e AAMAD_TARGET_RUNTIME
  - [ ] Nao embuta secrets; referencie apenas keys de `.env.example`
- [ ] Rode `*document-deploy`
  - [ ] Complete project-context/3.deliver/deploy.md (hosting, access control, rollback, Audit)
- [ ] Rode `*document-user-guide`
  - [ ] Complete project-context/3.deliver/user-guide.md
- [ ] Opcionalmente rode `aamad validate --phase deliver`.

---

### Step 7: Local MVP Launch

- [ ] Siga docs em setup.md e integration.md para rodar o MVP completo localmente
- [ ] Confirme que o MVP chat use case funciona end-to-end
- [ ] Revise todos os generated artifact files em project-context/2.build e 3.deliver

---

### Step 8: Prepare for Next Phase

- [ ] Arquive todos os MVP milestone artifacts em project-context/2.build e 3.deliver
- [ ] Liste todas as deferred/backlog features em qa.md e/ou como GitHub issues
- [ ] Compartilhe repo e context docs com a equipe ou comunidade para feedback

---

## Maintenance: Documentation sync

Apos debugging ou melhorias no codigo gerado de frontend, backend ou integration, artifacts podem ficar defasados em relacao a implementacao.

- [ ] Abra um chat novo e use `.cursor/prompts/prompt-sync-docs` (Claude Code: `/sync-docs`; VS Code: prompt sync-docs).
- [ ] Reconcilie `project-context/2.build/*.md` (e deploy.md se necessario) com a codebase atual.
- [ ] Acrescente Audit entries indicando action `sync-docs` em cada artifact atualizado.
- [ ] Rode novamente `aamad validate` para a fase relevante.

---

## Maintenance: Adopting evals in an existing project

Para projetos ja em QA ou apos QA sem uma evaluation criteria table na section 9 do SAD (criados antes desta capacidade existir). Este e o entry point normal para esses projetos, nao um fallback — nao exige voltar para Phase 1.

- [ ] Invoque `@qa.eng` e rode `*run-evals` diretamente.
- [ ] Responda as operator gap-check questions da skill (thresholds, SLA, risk tolerance, dataset provenance, judge calibration) no lugar da tabela SAD ausente.
- [ ] Extraia golden-dataset items do PRD e user stories, incluindo inputs contra os quais a implementacao atual nunca foi exercitada — nao construa o dataset apenas com casos que ja passam.
- [ ] Complete project-context/2.build/evals.md com thresholds acordados.
- [ ] Quando evals.md existir, preencha retroativamente a section 9 de sad.md a partir dele via `.cursor/prompts/prompt-sync-docs` para que futuras mudancas de model/prompt tenham um gate real.
- [ ] Rode novamente `aamad validate --phase build`.

---

> Para guidelines detalhadas e troubleshooting, veja [README.md](README.md) e a documentacao em `.cursor/templates` e `.cursor/rules`.

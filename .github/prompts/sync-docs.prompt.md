---
description: "AAMAD maintenance: sincronizar docs de project-context com a codebase"
agent: project-mgr
---
> NOTE: Use este prompt depois de depurar ou melhorar codigo gerado de frontend, backend ou integration para manter artefatos de project-context alinhados com a implementacao.
> NOTE: Prefira um contexto de chat novo. Nao invente features que nao existem na codebase; documente lacunas em Open Questions.

Voce esta sincronizando a documentacao AAMAD com o estado atual do software.

## Goal
Reconciliar artefatos em `project-context/` para que descrevam com precisao o codigo como ele existe agora.

## Inputs to load
- Source tree atual (frontend, backend, integration, deploy/CI configs)
- Artefatos existentes: `project-context/1.define/prd.md`, `sad.md` (read-only a menos que a architecture tenha mudado de fato)
- Build artifacts: `setup.md`, `frontend.md`, `backend.md`, `integration.md`, `qa.md`
- Opcional: `security.md`, `project-context/3.deliver/deploy.md`
- Opcional: `aamad.config.yml`

## Process
1. Compare declaracoes documentadas vs codigo real (endpoints, env vars, agent roles, UI flows, deploy commands).
2. Atualize artefatos markdown de Build (e Deliver, se presentes) para refletir a realidade.
3. Se a architecture mudou materialmente, proponha deltas de SAD em Open Questions ou atualize sad.md apenas quando o operador confirmar uma mudanca de architecture.
4. Preserve required headings: Sources, Assumptions, Open Questions, Audit.
5. Acrescente uma entrada de Audit em cada artifact modificado registrando action `sync-docs`, timestamp e o que mudou.

## Constraints
- Nao expanda silenciosamente o MVP scope nos docs alem do comportamento implementado.
- Nunca escreva valores de secrets em artifacts.
- Prefira Audit history aditiva em vez de apagar entradas anteriores de Audit.

## Output
- Markdown atualizado em `project-context/`
- Resumo curto dos arquivos alterados e Open Questions restantes

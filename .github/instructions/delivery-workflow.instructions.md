---
applyTo: '**'
name: Delivery Workflow Rules
description: Workflow Phase 3 Deliver para packaging, deployment config, CI scaffolding
  e access control
---

# AAMAD Delivery Workflow (Phase 3: Deliver)

## Purpose
- Operacionalizar o MVP validado depois que os Build-phase artifacts estiverem completos.
- Governar a persona DevOps Engineer (`@devops.eng`) e o deliver artifact unico `project-context/3.deliver/deploy.md`.

## Phase Gate
- Nao inicie Deliver work ate que `project-context/2.build/qa.md` exista e documente MVP verification results (pass ou known gaps explicitamente escopados).
- Prefira `project-context/2.build/evals.md` de `@qa.eng` antes de Deliver; suas Production Monitoring Recommendations alimentam a config de monitoring/observability em deploy.md. Se ausente, continue e registre a lacuna em Assumptions de deploy.md.
- Prefira `project-context/2.build/security.md` de `@security.eng` antes de Deliver. Se security.md estiver ausente, continue apenas quando o operador aceitar a lacuna e registre em Assumptions de deploy.md (obrigatorio quando `aamad.config.yml` define `security.require_security_assessment: true`).
- Required inputs: qa.md, backend.md, frontend.md, integration.md, PRD e SAD (incluindo DevOps and Deployment Architecture). Opcionais mas recomendados: evals.md, security.md.
- Em missing prerequisites, pare e escreva uma secao Diagnostic em deploy.md com blockers e safe retry steps.

## Deliver Module Structure
Execute delivery em passos focados com contexto novo quando possivel:

1. **Release readiness** — QA, evals, security gate check e release notes (`*prepare-release`).
2. **Deploy definition** — Container ou platform config alinhado ao runtime (`*define-deploy`).
3. **CI scaffolding** — Apenas config minima de pipeline lint/test/build (`*configure-cicd`).
4. **Runbook** — Hosting, env matrix, access control, rollback (`*document-deploy`).
5. **User documentation** — Installation guide e user manual (`*document-user-guide` → `user-guide.md`).

## Continuous Deployment Policy
- Gere apenas arquivos de configuracao CI/CD; nao acione live deploys sem autorizacao explicita do operador.
- Pipelines devem rodar lint, test e build stages adequados a stack definida em setup.md e backend.md.
- Documente manual promotion steps e rollback procedure em deploy.md.

## Hosting Environment
- Siga SAD DevOps and Deployment Architecture; use por default o menor target adequado ao MVP (single service ou compose stack).
- Alinhe runtime image e start command com `AAMAD_TARGET_RUNTIME` e a regra ativa do adapter.
- Registre hosting target, ports e health-check endpoints assumidos em Assumptions de deploy.md.

## Access Control
- Documente required secrets apenas como environment variable names (de `.env.example`); nunca escreva secret values em artifacts ou committed config.
- Descreva least-privilege access para runtime API keys, deployment credentials e chat endpoints em nivel de policy.
- Adie enterprise IAM, SSO e network segmentation para Future Work salvo escopo explicito em PRD/SAD.

## Artifact Contract
- Primary output: `project-context/3.deliver/deploy.md` com headings alinhados aos project templates quando aplicavel.
- Termine deploy.md com Sources, Assumptions, Open Questions e Audit (persona id, action, timestamp, resolved runtime).

## Failure Policy
- Pare em missing QA gate, unresolved runtime adapter ou pedidos para modificar application logic durante deliver.
- Quando o operador negar deploy authorization, complete apenas config e runbook e registre deployment status em Open Questions.
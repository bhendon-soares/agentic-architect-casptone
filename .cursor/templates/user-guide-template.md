# AAMAD User Guide Template

## Context & Instructions
Gere um installation guide e end-user manual a partir dos project artifacts.
Derive o conteudo de `setup.md`, `integration.md`, `deploy.md` e do PRD. Nao invente product capabilities que nao foram implementadas.

## Input Requirements

**PRD**: [REFERENCE `project-context/1.define/prd.md`]  
**setup.md**: [REFERENCE]  
**integration.md**: [REFERENCE]  
**deploy.md**: [REFERENCE]  
**security.md** (opcional): [REFERENCE]

## User Guide Structure — Generate All Sections Below

### 1. Product Overview

- O que o produto faz (1-2 paragrafos)
- Para quem ele e
- MVP limitations / known gaps

### 2. Prerequisites

- Runtime, OS, accounts e API keys (apenas env var **names**)
- Browsers ou clients suportados

### 3. Installation

- Passos de local install a partir de setup.md
- Configuration (incluindo keys de `aamad.config.yml` / `.env.example` quando relevante)
- Verificar health / smoke check

### 4. Getting Started

- Walkthrough de first-run do primary MVP flow (ex.: chat)
- Placeholders de screenshots apenas se necessario (descreva a UI, nao fabrique imagens)

### 5. Everyday Use

- Common tasks e expected outcomes
- Como interpretar agent responses / errors

### 6. Troubleshooting

- Common failures e remediations de integration.md / qa.md / deploy.md
- Onde encontrar logs

### 7. Deployment Notes (operators)

- Ponteiro resumido para o runbook em deploy.md
- Rollback overview (alto nivel)

## Sources

- Artifact paths usados

## Assumptions

- Environment assumptions nao verificadas no momento da escrita

## Open Questions

- Lacunas nos operator docs

## Audit

- Timestamp, persona id (`devops-eng`), action (`document-user-guide`), resolved `AAMAD_TARGET_RUNTIME`

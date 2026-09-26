# AAMAD Agent Framework

Este projeto usa o framework AAMAD para desenvolvimento multi-agent.
Framework version: 0.8.0
Veja as definicoes completas dos agentes nos diretorios especificos da IDE.

## Agent Personas
- **@product-mgr** — Product Manager: Orquestra visao de produto e requirements
- **@system.arch** — System Architect: Produz documentos SAD e SFS
- **@project.mgr** — Project Manager: Cria scaffold do projeto e environment
- **@frontend.eng** — Frontend Developer: Constroi a interface de chat MVP
- **@backend.eng** — Backend Developer: Constroi o backend para o runtime selecionado
- **@integration.eng** — Integration Engineer: Conecta frontend e backend
- **@qa.eng** — QA Engineer: Valida a funcionalidade do MVP (unit + integration)
- **@security.eng** — Security Engineer: Avalia seguranca do MVP antes de Deliver
- **@devops.eng** — DevOps Engineer: Empacota deploy/CI, runbook e user guide

## Workflow
1. **Define** (Phase 1): @product-mgr → elicitation → Market Research (opcional) → PRD → @system.arch → SAD
2. **Build** (Phase 2): @project.mgr → @frontend.eng / @backend.eng → @integration.eng → @qa.eng → @security.eng
3. **Deliver** (Phase 3): @devops.eng → deploy.md + user-guide.md

## Rules
Todo desenvolvimento segue as AAMAD core rules. Veja project-context/ para artifacts.
Rode `aamad validate` para verificar artifact quality gates.

## Agent Definitions
Veja `.github/agents/` para VS Code / GitHub Copilot agent definitions.

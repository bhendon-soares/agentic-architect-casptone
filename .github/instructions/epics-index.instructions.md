---
applyTo: '**'
name: Epics Index
description: Mapeamento de epics AAMAD para agent personas, actions e output artifacts
  para execucao AI modular baseada em regras.
---

# AAMAD Phase 2 and 3 Epics Index Rule

| Epic         | Persona        | Primary Output Artifact | PRD/SAD Section Reference      | Invocation        |
|--------------|---------------|------------------------|-------------------------------|-------------------|
| Architecture | @system.arch   | sad.md                 | SAD: Views & Decisions, PRD: Tech Req | *create-sad |
| Setup        | @project.mgr   | setup.md               | SAD: Environment, PRD: Setup   | *setup-project    |
| Frontend     | @frontend.eng  | frontend.md            | SAD: MVP UI, PRD: UI Scope     | *develop-fe       |
| Backend      | @backend.eng   | backend.md             | SAD: Crew Spec, PRD: Agent Def | *develop-be       |
| Integration  | @integration.eng | integration.md       | SAD: API & Flows, PRD: Int Req | *integrate-api    |
| QA           | @qa.eng        | qa.md                  | SAD: Testing, PRD: QA Plan     | *qa               |
| Evals        | @qa.eng        | evals.md               | SAD: Testing §9 (criteria table), PRD: Success Metrics | *run-evals |
| Security     | @security.eng  | security.md            | SAD: Security, PRD: Security   | *assess-security  |
| Deploy       | @devops.eng    | deploy.md              | SAD: DevOps & Deployment       | *prepare-release  |

## Execution Notes
- Cada persona trabalha de forma independente referenciando project-context/1.define/prd.md e sad.md.
- Build-phase artifacts ficam em project-context/2.build/; o Deliver artifact e project-context/3.deliver/deploy.md.
- Marque “future work” visivelmente na UI e nos docs conforme necessario.
- Atualize este index conforme epics avancam ou novas epics sao adicionadas.
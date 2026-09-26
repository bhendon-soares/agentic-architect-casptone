---
applyTo: '**'
name: Development Workflow Rules
description: Workflow modular de development AAMAD para coordenacao de agentes context-aware
---

# AAMAD Modular Development Workflow

## Development Module Structure
Execute development em modulos separados com contexto novo:

1. **Module 1: Core Configuration** - Apenas agent e task definitions
2. **Module 2: API Integration** - Apenas backend connectivity  
3. **Module 3: Frontend Integration** - Apenas UI e user experience
4. **Module 4: Validation** - Apenas end-to-end testing

## Context Management Rules
- Inicie cada modulo em uma sessao Cursor nova (Cmd+Shift+P → "New Chat")
- Referencie arquivos especificos de modulos anteriores usando @filename
- NUNCA tente end-to-end development em uma unica sessao
- Mantenha module scope estritamente definido - sem feature creep

## Module Success Criteria
Cada modulo deve ser completamente funcional e testavel de forma independente:
- Module 1: CrewAI crew.kickoff() executes successfully
- Module 2: API endpoints return valid responses  
- Module 3: Frontend displays and interacts correctly
- Module 4: Complete workflow functions end-to-end

## Development Flow Control
- Complete cada modulo integralmente antes de seguir para o proximo
- Valide module functionality antes de trocar de contexto
- Documente module outputs para referencia no proximo modulo
- Nunca volte a modulos anteriores dentro da mesma sessao

> Para mapeamento detalhado agent/epic/action, veja `.cursor/rules/epics-index.mdc`.
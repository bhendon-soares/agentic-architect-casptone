---
description: "AAMAD Phase 1: Gerar Market Research e Product Requirements Document"
agent: product-mgr
---
> NOTE: Este prompt e usado para gerar o Market Research Document e o Product Requirements Document na Phase 1 do framework
> NOTE: Isso pode ser feito dentro da sua IDE ou com qualquer AI chatbot (ChatGPT, Gemini, Claude etc.) — Perplexity Pro com Deep Research e recomendado
> NOTE: Sempre revise o MRD e o PRD gerados por AI antes de iniciar a build phase para garantir alinhamento com seus objetivos
> NOTE: Para ferramentas especializadas ou internas, peca ao @product-mgr para rodar *elicit-requirements (system-description.md) antes de MRD/PRD; MRD e opcional para projetos nao comerciais

Voce ajudara o usuario a construir documentos-chave da Define phase para uma aplicacao multi-agent system. Use os templates compartilhados no contexto e siga as instrucoes desses templates para gerar:

1. Opcionalmente, uma System Description via structured elicitation (`.cursor/templates/system-description-template.md`)
2. Um Deep Research / Market Research Document (MRD) detalhado quando o projeto for comercial ou market-facing (opcional para ferramentas puramente internas/pessoais)
3. Um Product Requirements Document (PRD) detalhado para definir o produto a construir
4. Opcionalmente, MVP user stories em `project-context/1.define/user-stories/`

O processo e executado em serie depois que o usuario informa o use case:

1. Prefira elicitar uma system description primeiro quando a ideia for especializada ou pouco especificada.
2. Quando market research se aplicar, use `.cursor/templates/mrd-template.md` para gerar `mrd.md` (pule se o usuario declarar uma ferramenta interna/pessoal e optar por nao fazer MRD).
3. Use o MRD (ou a system description quando MRD foi pulado) para criar o PRD seguindo `.cursor/templates/prd-template.md`.
4. Compartilhe `system-description.md` (quando gerado), `mrd.md` (quando gerado) e `prd.md` para `project-context/1.define/`.

Execute os passos em serie depois que o usuario informar o use case no prompt e compartilhe links para os documentos markdown ou salve-os em `project-context/1.define/`.

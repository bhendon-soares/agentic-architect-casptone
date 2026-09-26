# AAMAD Deep Research / Market Research Document (MRD) Template

## Context & Instructions
Voce esta conduzindo research abrangente para desenvolver um multi-agent system production-ready.
Baseie recomendacoes em evidencias. Trate o runtime selecionado (`AAMAD_TARGET_RUNTIME`) como uma escolha de implementacao para o MVP gerado, nao como a propria metodologia AAMAD.
Quando o projeto for interno ou pessoal e market research for pulado, nao force este documento; registre a decisao em Assumptions no PRD.

## Research Query Structure

**Primary Focus**: [INSERT YOUR MULTI-AGENT SYSTEM CONCEPT HERE]  
**Example**: "Customer Support AI Agent System for SaaS companies"  
**Selected Runtime** (opcional para research; obrigatorio depois em Build): [crewai | claude-agent-sdk | cursor-sdk]

## Research Dimensions — Investigate All Areas Below

### 1. Market Analysis & Opportunity Assessment

- **Market Size**: Tamanho atual e projetado do mercado para este dominio de aplicacao  
- **Growth Trends**: Projecoes de crescimento para 3 anos e fatores impulsionadores  
- **Market Gaps**: Necessidades especificas nao atendidas nas solucoes atuais  
- **Target Audience**: Personas detalhadas, pain points e willingness to pay  
- **Business Case**: Potencial de ROI e validacao da value proposition  
- **Competitive Landscape**: Competidores diretos e indiretos com analise de features

### 2. Technical Feasibility & Requirements Analysis

- **Runtime Capabilities**: Adequacao dos runtime adapters selecionados ou candidatos para este use case  
- **Agent Architecture Patterns**: Padroes multi-agent comprovados para este dominio  
- **Integration Requirements**: APIs, databases e third-party services necessarios  
- **Scalability Considerations**: Performance bottlenecks e scaling strategies  
- **Technical Risks**: Desafios de implementacao e abordagens de mitigacao  
- **Infrastructure Needs**: Cloud services, compute requirements e cost projections

### 3. User Experience & Workflow Analysis

- **User Journey Mapping**: Fluxos end-to-end de interacao com o multi-agent system  
- **Interface Requirements**: Necessidades de UI/UX para human-agent interaction  
- **Automation Opportunities**: Tarefas adequadas para automacao total vs parcial  
- **Human-in-the-Loop**: Quando e como supervisao humana e necessaria  
- **Success Metrics**: Outcomes mensuraveis e KPIs para efetividade do sistema  
- **User Adoption Factors**: Barreiras e facilitadores para aceitacao do usuario

### 4. Production & Operations Requirements

- **Deployment Architecture**: Cloud infrastructure e deployment strategies  
- **Monitoring & Observability**: Metrics essenciais e logging requirements  
- **Security Considerations**: Data protection, access control e compliance needs  
- **Maintenance & Updates**: Padroes de system update e version management  
- **Cost Structure**: Breakdown de custos de development, deployment e operacao  
- **Risk Assessment**: Riscos operacionais e business continuity planning

### 5. Innovation & Differentiation Analysis

- **Unique Value Propositions**: Como esta solucao difere das abordagens existentes  
- **Emerging Technologies**: Avancos relevantes de AI/ML e oportunidades de integracao  
- **Patent Landscape**: Patentes existentes e consideracoes de IP  
- **Future Trends**: Evolucao de tecnologia e mercado que afeta viabilidade de longo prazo  
- **Partnership Opportunities**: Aliancas estrategicas e possibilidades de integracao  
- **Monetization Strategies**: Revenue models e abordagens de pricing

## Output Format Requirements

### Executive Summary (2-3 paragraphs)

- **Market Opportunity**: Tamanho, crescimento e business case  
- **Technical Feasibility**: Complexidade de implementacao e probabilidade de sucesso  
- **Recommended Approach**: Direcao estrategica baseada nos research findings

### Detailed Findings by Dimension

Para cada uma das 5 research dimensions acima:

- **Key Insights**: 3-5 findings criticos com evidencias de suporte  
- **Data Points**: Metrics, estatisticas e evidencias quantitativas especificas  
- **Source Citations**: Research sources e datas de publicacao  
- **Implications**: Como findings impactam system design e business strategy

### Critical Decision Points

- **Go/No-Go Factors**: Requirements essenciais para viabilidade do projeto  
- **Technical Architecture Choices**: Recomendacoes de runtime e tecnologia  
- **Market Positioning**: Target market ideal e value proposition  
- **Resource Requirements**: Implicacoes de team, timeline e budget

### Risk Assessment Matrix

- **High Risk**: Ameacas criticas que exigem atencao imediata  
- **Medium Risk**: Consideracoes importantes para planejamento  
- **Low Risk**: Problemas menores a monitorar durante development

### Actionable Recommendations

- **Immediate Next Steps**: Acoes a tomar em ate 48 horas  
- **Short-term Priorities**: Foco de development para os proximos 30 dias  
- **Long-term Strategy**: Roadmap de 6-12 meses baseado nos findings

## Research Quality Requirements

- Cite pelo menos 15-20 authoritative sources  
- Inclua dados recentes (dentro de 18 meses quando possivel)  
- Forneca evidencia quantitativa para todas as major claims  
- Cruze findings entre multiplas fontes  
- Identifique informacoes conflitantes e forneca analise

## Sources

- Liste research sources, URLs e datas

## Assumptions

- Lacunas preenchidas por inferencia; rationale de market-skip se secoes foram abreviadas

## Open Questions

- Itens nao resolvidos para decisao de stakeholder ou architect

## Audit

- Timestamp, persona id (`product-mgr`), action (`create-mrd`), optional resolved `AAMAD_TARGET_RUNTIME`

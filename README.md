# Help Desk multiagente

Aplicação de suporte interno de TI em português brasileiro. Colaboradores fazem login para conversar sobre problemas técnicos, consultar orientações de uma base local de conhecimento e, quando necessário, abrir um incidente. O fluxo usa agentes CrewAI para triagem, consulta de fontes, resposta, validação de política e encaminhamento. Um console administrativo permite acompanhar conversas, tickets, fontes, eventos e métricas, além de gerenciar usuários.

O projeto combina React/TypeScript (frontend), FastAPI/Python (API) e PostgreSQL (persistência). Em desenvolvimento, a criação de tickets usa um adapter mock por padrão; a integração real com ServiceNow é opcional. O processamento de mensagens pelo CrewAI requer um modelo LLM configurado, mesmo usando tickets mock.

## Como funciona o atendimento

O [CrewAI](https://www.crewai.com/) organiza o trabalho de agentes de IA em etapas. Neste projeto, cada agente tem uma responsabilidade específica; o backend valida as decisões e controla a criação de tickets:

1. **IntakeTriageAgent:** classifica o pedido e identifica prioridade e riscos.
2. **KnowledgeAgent:** seleciona evidências da base local de conhecimento aprovada.
3. **ResponseAgent:** prepara uma resposta em português com referência à fonte ou propõe pedir mais informações ou abrir um ticket.
4. **QAPolicyAgent:** revisa a proposta e veta conteúdo inseguro ou instruções sem suporte documental.
5. **TicketingEscalationAgent:** quando a decisão é abrir um ticket, prepara os dados do incidente; não acessa o ServiceNow diretamente.

O chat e o histórico pertencem ao usuário autenticado. O administrador pode acompanhar atendimentos e tickets no console, além de gerenciar usuários.

## Integração com ServiceNow

Quando o atendimento exige escalonamento, o backend usa o adapter de incidentes. Por padrão, `TICKET_ADAPTER_MODE=mock` gera um número fictício sem enviar dados para fora. Com `TICKET_ADAPTER_MODE=servicenow`, o backend obtém um token OAuth e cria o incidente pela Table API do ServiceNow; o identificador retornado fica registrado localmente. Um envio com resultado incerto não é repetido automaticamente para evitar incidentes duplicados.

Para testar em uma instância sua, crie uma conta no [portal oficial ServiceNow Developer](https://developer.servicenow.com/) e solicite uma **Personal Developer Instance (PDI)** em *Manage > Instance* (ou *Request Instance*, conforme a interface). Configure na PDI um cliente OAuth e uma conta autorizada para criar incidentes. Depois, preencha no `.env` as variáveis `SERVICENOW_BASE_URL`, `SERVICENOW_INCIDENT_TABLE_PATH`, `SERVICENOW_AUTH_MODE=oauth`, `SERVICENOW_CLIENT_ID`, `SERVICENOW_CLIENT_SECRET`, `SERVICENOW_USERNAME` e `SERVICENOW_PASSWORD` conforme [.env.example](.env.example), e altere `TICKET_ADAPTER_MODE` para `servicenow`. Use somente dados fictícios ou redigidos na PDI: esse modo faz requisições reais.

## Pré-requisitos

- Git, Docker com Compose e Python 3.11 a 3.13.
- Node.js 20.19+ ou 22.12+ e npm.
- Uma chave de API do provedor LLM para testar o fluxo de conversa (exemplo abaixo com OpenAI).

## Executar localmente

Os comandos abaixo partem da raiz do repositório. Use terminais separados para o backend e o frontend.

### 1. Clonar e configurar o ambiente

```bash
git clone https://github.com/bhendon-soares/agentic-architect-casptone.git
cd agentic-architect-casptone
cp .env.example .env
openssl rand -hex 32
```

Edite `.env` com uma senha local para o banco (use a mesma em `POSTGRES_PASSWORD` e na URL), a chave gerada pelo último comando e as origens do frontend:

```dotenv
POSTGRES_PASSWORD=senha_local_do_banco
DATABASE_URL=postgresql+psycopg://support:senha_local_do_banco@127.0.0.1:5432/support
JWT_SECRET=cole_aqui_o_valor_gerado_pelo_openssl
APP_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
COOKIE_SECURE=false
KNOWLEDGE_BASE_PATH=../../knowledge
TICKET_ADAPTER_MODE=mock
LLM_MODEL=openai/gpt-4.1-mini
OPENAI_API_KEY=sua_chave_openai
```

Mantenha as demais variáveis do template como estão para o uso local. Se sua senha de banco contiver caracteres especiais, codifique-os na `DATABASE_URL` (percent-encoding). Não publique `.env` nem compartilhe `JWT_SECRET`, `POSTGRES_PASSWORD` ou chaves de API. O modo `mock` não envia tickets ao ServiceNow, mas as mensagens do chat ainda usam o provedor LLM configurado. Para detalhes da integração real, consulte a seção acima e o [contrato do backend](project-context/2.build/backend-funcional-spec.md).

### 2. Subir o banco de dados

```bash
docker compose up -d --wait db
```

O Compose inicia PostgreSQL 16 em `127.0.0.1:5432` e preserva os dados em um volume Docker. Se essa porta estiver ocupada, ajuste o mapeamento em [docker-compose.yml](docker-compose.yml) e a `DATABASE_URL`.

### 3. Instalar o backend e aplicar as migrações

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e src/backend
cd src/backend
../../.venv/bin/dotenv -f ../../.env run -- ../../.venv/bin/alembic upgrade head
```

### 4. Criar seu usuário administrador

Ainda em `src/backend`, execute (substitua e-mail e nome pelos seus):

```bash
../../.venv/bin/dotenv -f ../../.env run -- ../../.venv/bin/python -m app.cli create-admin --email voce@exemplo.com --name "Seu Nome"
```

Digite uma senha de pelo menos 12 caracteres quando solicitada no terminal. Ela não aparece na tela nem deve ser passada por argumento. Não há cadastro público: o primeiro admin é criado por este comando e pode cadastrar outros usuários no console.

### 5. Iniciar a API

Ainda em `src/backend`, mantenha este processo em execução:

```bash
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A documentação interativa da API fica em <http://127.0.0.1:8000/docs>. O backend carrega o `.env` da raiz automaticamente ao iniciar.

### 6. Iniciar o frontend

Em outro terminal, a partir da raiz do repositório:

```bash
cd src/frontend
npm ci
npm run dev
```

Acesse <http://localhost:5173/> e entre com o admin criado acima. O console administrativo está em <http://localhost:5173/admin>. O Vite encaminha `/api` para o backend na porta 8000. Se a porta do frontend mudar, adicione a nova origem em `APP_ALLOWED_ORIGINS` e reinicie a API.

## Estrutura e verificação

- [src/frontend](src/frontend): chat, autenticação e console administrativo.
- [src/backend](src/backend): API, fluxo CrewAI, migrações, adapter de tickets e testes.
- [knowledge](knowledge): fontes locais de orientação para o atendimento.
- [project-context](project-context): requisitos, arquitetura e especificações do projeto.

Para rodar os testes e verificações locais, a partir da raiz do repositório e com o banco acessível para os testes de migração:

```bash
.venv/bin/pip install -e 'src/backend[dev]'
.venv/bin/python -m pytest -q src/backend/tests
.venv/bin/ruff check src/backend/app src/backend/tests
cd src/frontend
npm test
npm run typecheck
```

## Desenvolvimento com AAMAD

Este projeto foi desenvolvido com o framework AAMAD. Para ajustes e melhorias, você pode usar os agentes disponíveis em [.github/agents](.github/agents) e os artefatos em [project-context](project-context). Para saber mais sobre o framework, consulte o [repositório do AAMAD](https://github.com/synaptic-ai-consulting/AAMAD).
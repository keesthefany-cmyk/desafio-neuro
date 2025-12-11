# 🤖 **Neurotech Onboarding System — IA Multiagente para Onboarding Automatizado**

## 🎯 Visão Geral

Sistema inteligente de **onboarding automatizado** para novos funcionários utilizando:

- **IA Multiagente com AutoGen** (GraphFlow coordenado)
- **Coleta automática de 8 campos obrigatórios**
- **Armazenamento automático de dados ao completar** (sem ações manuais)
- **Busca inteligente com Elasticsearch (RAG)**
- **FastAPI como gateway HTTP**
- **Redis como fila de mensagens e gerenciamento de estado**
- **Infraestrutura Docker Compose**
- **Deduplicação de mensagens multi-layer** (user, coordinator, talker)

A solução automatiza completamente o fluxo de onboarding, coletando dados conversacionalmente e armazenando quando todos os 8 campos forem preenchidos.

---

# 🏗️ Arquitetura do Sistema

## 📊 Diagrama de Fluxo

```
Usuário (WhatsApp)
    ↓
POST /api/onboarding/message
    ↓
FastAPI → Input Buffer (Redis)
    ↓
QueueManager (income_messages)
    ↓
AiOrchestrator.execute()
    ├→ User Message Processing (deduplicated)
    ├→ Coordinator Agent (single execution per run)
    ├→ Talker Agent (single response per run)
    └→ Auto-store if complete (8 fields)
    ↓
Output Queue (Redis) → WhatsApp
```

## 🤖 Três Agentes Coordenados (GraphFlow)

### 1️⃣ **Coordinator Agent**
- Gerencia o fluxo de coleta de dados
- Solicita campos um por um (conversacional)
- Passa controle para o Talker enviar resposta
- Executa exatamente 1 vez por rodada (deduplicado)

### 2️⃣ **Talker Agent**
- Envia as mensagens ao usuário final
- Formata respostas com linguagem amigável
- Aguarda o Coordinator autorizar
- Gera exatamente 1 resposta por rodada (deduplicado com hash)

### 3️⃣ **Finalizer Agent** (opcional, não ativo no fluxo atual)
- Encerrar processos
- Gerar confirmações finais

---

# 📋 Fluxo de Coleta de Dados

O sistema coleta **8 campos obrigatórios** em ordem fixa:

| Campo | Tipo | Exemplo |
|-------|------|---------|
| 1️⃣ **Nome Completo** | texto | "João Silva Santos" |
| 2️⃣ **CPF** | CPF | "123.456.789-00" |
| 3️⃣ **Data de Nascimento** | data | "15/03/1990" |
| 4️⃣ **Cargo** | texto | "Desenvolvedor Python" |
| 5️⃣ **Email Corporativo** | email | "joao.silva@neurotech.com" |
| 6️⃣ **Banco** | texto | "Banco do Brasil" |
| 7️⃣ **Agência** | número | "1234-5" |
| 8️⃣ **Conta Bancária** | número | "987654-3" |

### ⚙️ Comportamento Automático

1. **Coleta conversacional**: Coordinator solicita 1 campo por vez
2. **Extração automática**: Sistema extrai valor da mensagem do usuário
3. **Incremento**: Avança para próximo campo
4. **Detecção de completude**: Quando 8 campos ≥ preenchidos
5. **Armazenamento automático**: Chama `store_employee_data()` automaticamente via tool

**Nenhuma ação manual necessária** — tudo é automático ao atingir 8 campos!

---

# 💻 Tecnologias Utilizadas

| Tecnologia | Versão | Propósito |
|-----------|--------|----------|
| **AutoGen** | 0.4.9 | Orquestração multiagente + GraphFlow |
| **FastAPI** | 0.104.0+ | HTTP API e webhooks |
| **Redis** | 7 (Alpine) | Filas de mensagens e estado |
| **Elasticsearch** | 8.11.0 | Base de conhecimento (RAG) |
| **OpenAI** | 1.30.0+ | Modelo GPT-4o-mini (temp=0.2) |
| **Pydantic** | 2.0.0+ | Validação de dados |
| **HTTPX** | 0.25.0+ | Requisições assíncronas |
| **Python** | 3.11+ | Ambiente de execução |

---

# 💬 Fluxo da Conversação

Usuário → WhatsApp → Webhook → API FastAPI  
↓  
ConversationManager  
↓  
Redis Queue  
↓  
Coordinator Agent  
↓  
(Talker, Tools, Finalizer)  
↓  
Resposta  
↓  
WhatsApp do usuário

---

# 🚀 Instalação e Execução

## 📋 Pré-requisitos

- Docker & Docker Compose instalados
- Python 3.11+ (para rodar localmente sem Docker)
- Variáveis de ambiente configuradas

## 1️⃣ Clonar e Configurar

```bash
git clone https://github.com/keesthefany-cmyk/desafio-neuro.git
cd desafio-neuro
```

## 2️⃣ Criar arquivo `.env`

```bash
cat > .env << EOF
# OpenAI
OPENAI_API_KEY=sk-proj-xxxxx

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# Elasticsearch
ES_HOST=http://elasticsearch:9200
ES_PORT=9200

# API
PORT=8000
HOST=0.0.0.0

# Logging
LOG_LEVEL=DEBUG
EOF
```

## 3️⃣ Iniciar com Docker Compose

```bash
docker compose up -d --build
```

### 📡 Serviços Disponíveis

| Serviço | URL/Porta | Status |
|---------|-----------|--------|
| **API Onboarding** | `http://localhost:8000` | POST `/api/onboarding/message` |
| **Redis** | `localhost:6379` | Cache + Filas |
| **Elasticsearch** | `http://localhost:9200` | RAG + Busca |
| **Health Check** | `GET /api/health/openai` | Teste OpenAI |

---

## ▶️ Usar Localmente (sem Docker)

```bash
# 1. Criar ambiente virtual
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate (Windows)

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar Redis (via docker ou local)
redis-server

# 4. Rodar a API
python main.py
```

A API estará em `http://localhost:8000`

---

# 🔌 Endpoints da API

## POST `/api/onboarding/message`

Envia uma mensagem para o sistema de onboarding.

**Request:**
```json
{
  "chat_key": "session-123",
  "user_type": "funcionario",
  "phone": "5581999999999",
  "message": "João Silva"
}
```

**Response:**
```json
{
  "status": "success",
  "chat_key": "session-123",
  "message": "Qual seu CPF?"
}
```

## GET `/api/health/openai`

Testa conexão com OpenAI.

**Response:**
```json
{
  "status": "openai_api_ready",
  "model": "gpt-4o-mini",
  "connection": "ok"
}
```

---

# 📁 Estrutura do Projeto

```
desafio-neuro/
├── main.py                          # Entrada FastAPI
├── tasks.py                         # Loop de resposta async
├── requirements.txt                 # Dependências
├── docker-compose.yml               # Orquestração
├── Dockerfile                       # Build da API
│
├── app/
│   ├── agents/                      # Agentes AutoGen
│   │   ├── agent_builder.py        # Construtor de agentes
│   │   ├── agent_factory.py        # Factory de criação
│   │   ├── user_proxy_agent.py     # Agente proxy do usuário
│   │   └── agent_config.py         # Configurações
│   │
│   ├── services/                    # Serviços core
│   │   ├── ai_orchestrator.py      # Orquestrador principal (CRITICAL)
│   │   ├── queue_manager.py        # Redis + filas
│   │   ├── conversation_manager.py # Histórico de chat
│   │   ├── message_processor.py    # Parsing de mensagens
│   │   └── orchestrator_registry.py # Cache de orquestradores
│   │
│   ├── tools/                       # Ferramentas dos agentes
│   │   └── tools.py                # store_employee_data, search_kb, etc
│   │
│   ├── configs/                     # Configurações
│   │   ├── config.py               # Constantes e paths
│   │   └── logging_config.py       # Setup de logs
│   │
│   ├── templates/                   # Prompts e rules
│   │   ├── prompts.yaml            # Instruções dos agentes
│   │   └── rules.yaml              # Regras de negócio
│   │
│   ├── data/                        # Dados estáticos
│   │   ├── neurotech.json          # Base de conhecimento
│   │   └── politicas.json          # Políticas da empresa
│   │
│   └── model/                       # Modelos Pydantic
│       └── requests/
│           └── remote_user_message.py
│
├── data/                            # Dados de produção
│   ├── employees/                   # Dados de funcionários
│   └── (MongoDB será aqui se usado)
│
└── logs/                            # Arquivos de log
```

---

# 🔑 Componentes Críticos

## `AiOrchestrator` (app/services/ai_orchestrator.py)

**Responsabilidade**: Orquestra todo o fluxo de IA

### Métodos principais:

- `prepare()`: Inicializa agentes e GraphFlow uma única vez
- `execute(message)`: Executa GraphFlow com mensagem do usuário
- `_run_graph_flow_stream()`: Loop de execução com deduplicação multi-layer
  - `user_message_processed`: Flag para processar user message 1x
  - `coordinator_executed`: Flag para executar coordinator 1x
  - `processed_talker_messages`: Hash set para talker 1x
- `_update_collected_data_from_message()`: Extrai dados conversacionalmente
- `_is_collection_complete()`: Detecta quando 8 campos ≥ preenchidos
- `_store_collected_data()`: Chama tool para armazenar automaticamente

## `QueueManager` (app/services/queue_manager.py)

Gerencia todas as operações Redis:
- `income_messages`: Fila de entrada
- `outcome_queue`: Fila de saída global
- Chat state tracking (waiting_user_response, accumulating_first_interaction)

## `ConversationManager` (app/services/conversation_manager.py)

Persiste histórico de conversa e detecta finalizações.

---

# 🎯 Fluxo Detalhado: Do Usuário ao Armazenamento

```
1. Usuário envia mensagem no WhatsApp
   └─> POST /api/onboarding/message

2. FastAPI valida e enfileira
   └─> input_buffer (Redis)

3. QueueManager processa
   └─> income_messages (formatado com metadata)

4. AiOrchestrator.execute() é chamado
   └─> Prepara GraphFlow se primeira vez
   └─> Extrai user message (1x)
   └─> Coordinator gera instrução (1x)
   └─> Talker formata resposta (1x)
   └─> Sistema detecta 8 campos coletados?
       └─> SIM: Chama store_employee_data()
       └─> NÃO: Continua aguardando próximo campo

5. Resposta é enfileirada globalmente
   └─> outcome_queue (Redis)

6. tasks.py (reply_loop) consome
   └─> Envia para WhatsApp do usuário

7. Repetir até onboarding completo
```

---

# 🧪 Testando o Sistema

## Teste rápido via curl

```bash
curl -X POST http://localhost:8000/api/onboarding/message \
  -H "Content-Type: application/json" \
  -d '{
    "chat_key": "test-session",
    "user_type": "funcionario",
    "phone": "5581999999999",
    "message": "João Silva"
  }'
```

## Teste via script Python

```bash
python test_onboarding_flow.py
```

## Ver logs em tempo real

```bash
docker compose logs -f onboarding-api
```

Procure por:
- ✅ `[chat:session-xxx] Campo atualizado` — Campo coletado
- ✅ `Todos os 8 campos coletados!` — Pronto para armazenar
- ✅ `store_employee_data chamado` — Dados salvos

---

# 🔍 Monitoramento e Debugging

## Health Checks

```bash
# OpenAI
curl http://localhost:8000/api/health/openai

# MCP (se disponível)
curl http://localhost:8000/api/health/mcp

# Redis
redis-cli ping  # PONG se online

# Elasticsearch
curl http://localhost:9200/_cluster/health
```

## Logs estruturados

Todos os logs estão em `/logs/` com timestamps e níveis:

```
2025-12-11 00:49:22,465 [INFO] app.services.ai_orchestrator: [chat:session-123] Campo atualizado: Nome = João Silva
2025-12-11 00:49:22,467 [DEBUG] app.services.ai_orchestrator: [chat:session-123] coordinator: {...}
```

## Chaves Redis relevantes

```bash
# Ver filas ativas
redis-cli KEYS "chat:*"

# Inspecionar income messages
redis-cli LRANGE "chat:session-123:income_messages" 0 -1

# Inspecionar estado
redis-cli GET "chat:session-123:status"
```

---

# ⚙️ Configuração Avançada

## Modificar Prompts dos Agentes

Edite `app/templates/prompts.yaml`:

```yaml
coordinator_system_prompt: |
  Você é um assistente especializado em onboarding...
  
talker_system_prompt: |
  Você é responsável por...
```

Mudanças entram em efeito imediatamente no próximo `execute()`.

## Adicionar Campos à Coleta

1. Edite `_update_collected_data_from_message()` em `ai_orchestrator.py`
2. Atualize o mapeamento de campos
3. Aumente o limite de `_is_collection_complete()` de 8 para N

## Customizar Tool de Armazenamento

Edite `app/tools/tools.py` → `store_employee_data_tool()`:

```python
async def store_employee_data_tool(user_id: str, status: str, data: dict):
    # Conectar com seu banco (MongoDB, PostgreSQL, etc)
    # Persistir dados
    pass
```

---

# 📊 Entendendo a Deduplicação Multi-Layer

O sistema previne **3 tipos de duplicatas** simultaneamente:

### 1. User Message Deduplication
**Problema**: GraphFlow pode passar user message múltiplas vezes no loop
**Solução**: `user_message_processed = False` → marcado como `True` na primeira

### 2. Coordinator Deduplication
**Problema**: Coordinator pode executar > 1x no mesmo run
**Solução**: `coordinator_executed = False` → `continue` se já executado

### 3. Talker Message Deduplication
**Problema**: Talker pode enviar mesma mensagem N vezes
**Solução**: Hash-based tracking com `processed_talker_messages` set

**Resultado**: Exatamente 1 mensagem do talker por execute()

---

# 🐛 Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| "Chat key not found" | Session expirou no Redis | Cache TTL muito curto em `queue_manager.py` |
| Talker envia 2 mensagens | Coordinator executou 2x (BUG ANTIGO) | ✅ Corrigido com `coordinator_executed` flag |
| Campo não coletado | Prompt do coordinator confuso | Edite prompts.yaml, simplifique instruções |
| Armazenamento não funciona | Tool não implementada | Implemente `store_employee_data_tool()` em tools.py |
| Elasticsearch offline | Porta 9200 não acessível | `docker compose ps` e verifique saúde |
| Redis full | Limpeza de dados antigos faltando | `FLUSHDB` periodicamente ou TTL automático |

---

# 📝 Contribuindo

1. Criar branch: `git checkout -b feature/sua-feature`
2. Commit: `git commit -am "Descrição da mudança"`
3. Push: `git push origin feature/sua-feature`
4. Abrir Pull Request

### Padrões de código
- Use type hints (`from typing import ...`)
- Logs via `logger.debug()`, `logger.info()`
- Async/await para I/O (Redis, OpenAI)
- Docstrings em funções críticas

---


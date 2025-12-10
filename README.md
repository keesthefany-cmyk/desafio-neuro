# 📘 **SOFIA — Sistema de Atendimento Externo com IA Multiagente**

## 🧠 Visão Geral

Este projeto implementa o **SOFIA — Sistema de Onboarding e Fluxos Inteligentes Automatizados**, uma plataforma de atendimento via WhatsApp totalmente automatizada utilizando:

- **IA Multiagente com AutoGen 0.7.4**
- **Fluxos coordenados entre agentes especializados**
- **Busca inteligente com Elasticsearch (RAG)**
- **FastAPI como gateway HTTP**
- **Redis como fila e estado conversacional**
- **Integração com WhatsApp via Webhook**
- **Infraestrutura Docker**

A solução permite criar conversas complexas, com agentes especializados coordenando tarefas de onboarding, atendimento, análise de documentos, busca de conhecimento e finalização de processos.

---

# 🧩 Arquitetura Multiagente (AutoGen 0.7.4)

O sistema trabalha com **3 agentes principais**, coordenados pelo `AiOrchestrator`:

### 🔹 Coordinator Agent
Gerencia o fluxo. Decide quando chamar ferramentas (OCR, RAG, validações). Encaminha tarefas para os demais agentes.

### 🔹 Talker Agent
Responsável pela comunicação com o usuário.  
Formatos de resposta, explicações, coleta de dados e orientações.

### 🔹 Finalizer Agent
Fecha o processo, conclui etapas e envia a mensagem final ao usuário.

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

# 🏗️ Tecnologias Utilizadas

| Módulo | Função |
|-------|--------|
| **FastAPI** | Entrada de mensagens + Webhook |
| **Redis** | Fila + armazenamento de estado |
| **Elasticsearch 8.11** | Base de conhecimento RAG |
| **AutoGen 0.7.4** | Orquestração multiagente |
| **OpenAI / Gemini** | Processamento de linguagem |
| **Docker Compose** | Orquestração da infraestrutura |
| **Pydantic** | Validação de dados |
| **HTTPX** | Requests assíncronas |

---

# 📦 Instalação

## 1️⃣ Clonar o repositório
```
git clone https://github.com/seu_repo/sofia.git
cd sofia
```

## 2️⃣ Criar o arquivo `.env`
Exemplo:

```
OPENAI_API_KEY=SUA_CHAVE
REDIS_HOST=redis
REDIS_PORT=6379
ES_HOST=http://elasticsearch:9200
PORT=7000
```

## 3️⃣ Subir toda a infraestrutura
```
docker compose up -d --build
```

| Serviço | Porta |
|--------|-------|
| API | 7000 |
| Redis | 6379 |
| Elasticsearch | 9200 |

---

# ▶️ Rodar localmente (sem Docker)

```
pip install -r requirements.txt
python main.py
```

---

# 🧪 Testes de Saúde

### FastAPI:
```
curl http://localhost:7000/api/health
```

### OpenAI:
```
curl http://localhost:7000/api/health/openai
```

---

# 🗃️ Estrutura de Pastas

```
app/
 ├─ agents/
 │   ├─ agent_factory.py
 │   ├─ user_proxy_agent.py
 │   └─ ...
 ├─ services/
 │   ├─ orchestrator.py
 │   ├─ queue_manager.py
 │   ├─ conversation_manager.py
 │   └─ tools_service.py
 ├─ configs/
 │   ├─ config.py
 │   ├─ logging_config.py
 │   └─ prompts/
 ├─ core/
 │   ├─ states.py
 │   ├─ logger.py
 │   └─ utils.py
 ├─ main.py
 ├─ tasks.py
 └─ ...
```

---

# 🛠️ Ferramentas suportadas (MCP)

O Coordinator pode acionar:

- 🔍 `search_knowledge_base_tool`
- 📄 `process_document_ocr_tool`
- 🧾 `store_employee_data_tool`
- 🔄 `update_knowledge_base_tool`
- 📌 `check_onboarding_status_tool`

---

# 📨 Webhook de Entrada

```
POST /api/messages/webhook
```
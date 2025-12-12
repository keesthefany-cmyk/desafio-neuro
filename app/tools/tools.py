import os
import json
import base64
import traceback
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from functools import wraps


from elasticsearch import Elasticsearch
from openai import OpenAI
import google.generativeai as genai


from autogen_core.tools import FunctionTool
from app.configs.logging_config import configurar_logger
from app.configs.config import ElasticsearchConstants, LLMProviderConstants


logger = configurar_logger(__name__)


# ==============================================================
# CLIENTES
# ==============================================================


openai_client = OpenAI(api_key=LLMProviderConstants.OPENAI_API_KEY)
genai.configure(api_key=LLMProviderConstants.GEMINI_API_KEY)


es_client = Elasticsearch(
    [ElasticsearchConstants.ES_HOST],
    basic_auth=(
        ElasticsearchConstants.ES_USER,
        ElasticsearchConstants.ES_PASSWORD
    ),
    verify_certs=False
)


EMPLOYEES_DATA_DIR = Path("./data/employees")
EMPLOYEES_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==============================================================
# ✅ NOVO: DECORATOR PARA LOGAR TOOLS
# ==============================================================


def log_tool_execution(func):
    """
    ✅ NOVO: Decorator que registra execução de tools com detalhes completos
    
    Registra:
    - Início da execução
    - Parâmetros recebidos
    - Sucesso/Erro
    - Resultado
    - Tempo de execução
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__name__
        
        # Extrai parâmetros legíveis
        params = {}
        if kwargs:
            params = {k: str(v)[:50] for k, v in kwargs.items()}
        
        logger.info(
            "🔧 [TOOL CALL] %s() iniciado | Params: %s",
            func_name,
            params
        )
        
        try:
            result = await func(*args, **kwargs)
            
            # Verifica sucesso
            success = result.get("success", None) if isinstance(result, dict) else True
            result_preview = str(result)[:100] if result else "None"
            
            if success:
                logger.info(
                    "✅ [TOOL SUCCESS] %s() concluído | Resultado: %s",
                    func_name,
                    result_preview
                )
            else:
                error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else "Unknown"
                logger.warning(
                    "⚠️  [TOOL WARNING] %s() | Erro: %s",
                    func_name,
                    error_msg
                )
            
            return result
            
        except Exception as e:
            logger.error(
                "❌ [TOOL ERROR] %s() | Erro: %s | Tipo: %s | Traceback: %s",
                func_name,
                str(e)[:100],
                type(e).__name__,
                traceback.format_exc()[:200]
            )
            raise
    
    return async_wrapper


# ==============================================================
# EMBEDDING
# ==============================================================


def generate_embedding(text: str) -> List[float]:
    """Gera embedding de texto usando OpenAI"""
    try:
        resp = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        logger.debug("📊 Embedding gerado para texto com %d caracteres", len(text))
        return resp.data[0].embedding
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        raise


# ==============================================================
# TOOL 1: SEARCH_KNOWLEDGE_BASE (RAG)
# ==============================================================


@log_tool_execution  # ✅ NOVO: Decorator
async def search_knowledge_base(
    query: str,
    base_type: str = "neuro",
    top_k: int = 3,
    user_type: str = "funcionario"
) -> Dict[str, Any]:
    """
    ✅ Busca semântica na base de conhecimento usando Elasticsearch.
    
    Args:
        query: Pergunta do usuário
        base_type: "neuro" ou "politicas"
        top_k: Número de resultados (default: 3)
        user_type: "funcionario" ou "rh"
    
    Returns:
        Dict com sucesso, query e resultados
        
    Exemplo de uso:
        result = await search_knowledge_base("Qual é o salário?", base_type="neuro")
        if result["success"]:
            for item in result["results"]:
                print(item["content"])
    """
    
    INDEX_MAP = {
        "neuro": ElasticsearchConstants.NEURO_BASE_INDEX,
    }
    
    if base_type not in INDEX_MAP:
        return {
            "success": False,
            "error": f"base_type inválido: {base_type}",
        }
    
    index_name = INDEX_MAP[base_type]
    
    try:
        logger.debug("🔍 Gerando embedding para query: %s", query[:50])
        embedding = generate_embedding(query)
    except:
        return {
            "success": False,
            "error": "Erro ao gerar embedding"
        }
    
    try:
        logger.debug("🔎 Consultando Elasticsearch índice: %s | top_k: %d", index_name, top_k)
        
        response = es_client.search(
            index=index_name,
            knn={
                "field": "embedding",
                "query_vector": embedding,
                "k": top_k,
                "num_candidates": top_k * 10
            }
        )
        
        hits = response["hits"]["hits"]
        logger.debug("📊 %d resultados encontrados", len(hits))
        
    except Exception as e:
        logger.error(f"Erro ao consultar Elasticsearch: {e}")
        return {
            "success": False,
            "error": f"Erro ao consultar índice {index_name}",
        }
    
    results = []
    for h in hits:
        src = h["_source"]
        results.append({
            "id": h["_id"],
            "score": h["_score"],
            "title": src.get("title"),
            "category": src.get("category"),
            "content": src.get("content"),
            "tags": src.get("tags", []),
            "department": src.get("department"),
            "last_updated": src.get("last_updated"),
        })
    
    return {
        "success": True,
        "query": query,
        "base_type": base_type,
        "results_count": len(results),
        "results": results,
    }
@log_tool_execution 
async def search_politicas_base(
    query: str,
    base_type: str = "politicas",
    top_k: int = 3,
    user_type: str = "funcionario"
) -> Dict[str, Any]:
    """
    ✅ Busca semântica na base de conhecimento usando Elasticsearch.
    
    Args:
        query: Pergunta do usuário
        base_type: "politicas"
        top_k: Número de resultados (default: 3)
        user_type: "funcionario" ou "rh"
    
    Returns:
        Dict com sucesso, query e resultados


    """
    
    INDEX_P = {
        "politicas": ElasticsearchConstants.POLITICAS_BASE_INDEX,
    }
    
    if base_type not in INDEX_P:
        return {
            "success": False,
            "error": f"base_type inválido: {base_type}",
        }
    
    index_name = INDEX_P[base_type]
    
    try:
        logger.debug("🔍 Gerando embedding para query: %s", query[:50])
        embedding = generate_embedding(query)
    except:
        return {
            "success": False,
            "error": "Erro ao gerar embedding"
        }
    
    try:
        logger.debug("🔎 Consultando Elasticsearch índice: %s | top_k: %d", index_name, top_k)
        
        response = es_client.search(
            index=index_name,
            knn={
                "field": "embedding",
                "query_vector": embedding,
                "k": top_k,
                "num_candidates": top_k * 10
            }
        )
        
        hits = response["hits"]["hits"]
        logger.debug("📊 %d resultados encontrados", len(hits))
        
    except Exception as e:
        logger.error(f"Erro ao consultar Elasticsearch: {e}")
        return {
            "success": False,
            "error": f"Erro ao consultar índice {index_name}",
        }
    
    results = []
    for h in hits:
        src = h["_source"]
        results.append({
            "id": h["_id"],
            "score": h["_score"],
            "title": src.get("title"),
            "category": src.get("category"),
            "content": src.get("content"),
            "tags": src.get("tags", []),
            "department": src.get("department"),
            "last_updated": src.get("last_updated"),
        })
    
    return {
        "success": True,
        "query": query,
        "base_type": base_type,
        "results_count": len(results),
        "results": results,
    }


# ==============================================================
# TOOL 2: STORE_EMPLOYEE_DATA
# ==============================================================


@log_tool_execution  # ✅ NOVO: Decorator
async def store_employee_data(
    user_id: str,
    data_type: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    ✅ Armazena dados do funcionário em UM ÚNICO JSON com progresso integrado (SIMPLIFICADO PARA TESTES).
    
    Args:
        user_id: ID único do funcionário (usado como nome do arquivo)
        data_type: "dados_pessoais", "contato", "documento"
        data: Dict com os dados a salvar
    
    Returns:
        Dict com sucesso, dados salvos e progresso atualizado
        
    Estrutura salva em ./data/employees/{user_id}.json:
        {
            "user_id": "session-123",
            "nome_completo": "João Silva",
            "created_at": "2025-12-12T01:21:00",
            "updated_at": "2025-12-12T01:21:30",
            "dados_pessoais": {
                "nome_completo": "João Silva",
                "cpf": "123.456.789-00",
                "data_nascimento": "01/01/1990",
                "cargo": "Desenvolvedor"
            },
            "contato": {
                "forma_pagamento": "pix"
            },
            "documentos": [
                {
                    "tipo": "cpf",
                    "numero": "12345678900",
                    "timestamp": "2025-12-12T01:21:30"
                }
            ],
            "onboarding_status": {
                "progresso": 100,
                "status": "completo"
            }
        }
    """
    
    try:
        employee_file = EMPLOYEES_DATA_DIR / f"{user_id}.json"
        
        # ✅ Carrega arquivo existente ou cria novo
        if employee_file.exists():
            logger.debug("📂 Carregando arquivo existente de %s", user_id)
            with open(employee_file, 'r', encoding='utf-8') as f:
                employee_data = json.load(f)
        else:
            logger.debug("📝 Criando novo arquivo para %s", user_id)
            employee_data = {
                "user_id": user_id,
                "nome_completo": "",  # ✅ NOVO: Nome no topo para fácil visualização
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "dados_pessoais": {},
                "contato": {},
                "documentos": [],
                "onboarding_status": {
                    "progresso": 0,
                    "status": "em_andamento"
                }
            }
        
        # ✅ Armazena dados de acordo com tipo
        if data_type == "documento":
            employee_data["documentos"].append({
                **data,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug("📄 Documento adicionado: %s", data.get("tipo", "unknown"))
            
        elif data_type in ["dados_pessoais", "contato"]:
            employee_data[data_type].update(data)
            
            # ✅ NOVO: Atualiza nome no topo se dados_pessoais foi preenchido
            if data_type == "dados_pessoais" and "nome_completo" in data:
                employee_data["nome_completo"] = data["nome_completo"]
                logger.debug("📝 Nome atualizado no topo: %s", data["nome_completo"])
            
            logger.debug("💾 %s atualizado", data_type)
        else:
            employee_data[data_type] = data
            logger.debug("💾 Campo %s adicionado", data_type)
        
        employee_data["updated_at"] = datetime.now().isoformat()
        
    
        total_steps = 3
        completed = 0
        
        if employee_data["dados_pessoais"]:
            completed += 1
        if employee_data["contato"]:
            completed += 1
        if employee_data["documentos"]:
            completed += 1
        
        progresso = int((completed / total_steps) * 100)
        employee_data["onboarding_status"]["progresso"] = progresso
        
        if progresso >= 100:
            employee_data["onboarding_status"]["status"] = "completo"
        
        # ✅ Salva ÚNICO arquivo JSON com tudo junto
        with open(employee_file, 'w', encoding='utf-8') as f:
            json.dump(employee_data, f, indent=2, ensure_ascii=False)
        
        logger.info(
            "💾 [%s] Dados salvos | Tipo: %s | Progresso: %d%% | Nome: %s",
            user_id,
            data_type,
            progresso,
            employee_data.get("nome_completo", "Sem nome")
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "nome_completo": employee_data.get("nome_completo", ""),
            "data_type": data_type,
            "file_path": str(employee_file),
            "progresso": progresso,
            "status": employee_data["onboarding_status"]["status"],
            "campos_completos": {
                "dados_pessoais": bool(employee_data["dados_pessoais"]),
                "contato": bool(employee_data["contato"]),
                "documentos": bool(employee_data["documentos"])
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(
            "❌ Erro ao salvar dados de %s: %s\n%s",
            user_id,
            str(e),
            traceback.format_exc()
        )
        return {
            "success": False,
            "error": f"Erro ao salvar dados: {str(e)}"
        }


# ==============================================================
# TOOL 3: UPDATE_KNOWLEDGE_BASE (RH atualiza políticas)
# ==============================================================


@log_tool_execution  # ✅ NOVO: Decorator
async def update_knowledge_base(
    action: str,
    document_title: str,
    content: str = "",
    category: str = "politicas",
    rh_user_id: str = "",
    user_type: str = "rh"
) -> Dict[str, Any]:
    """
    ✅ Atualiza base de conhecimento no Elasticsearch (apenas RH).
    
    Args:
        action: "add", "update", "remove"
        document_title: Título do documento
        content: Conteúdo do documento
        category: Categoria (politicas, beneficios, procedimentos)
        rh_user_id: ID do usuário RH
        user_type: Deve ser "rh" para ter acesso
    
    Returns:
        Dict com sucesso e detalhes da operação
        
    Exemplo:
        result = await update_knowledge_base(
            action="add",
            document_title="Nova Política de Férias",
            content="Cada funcionário tem direito a 30 dias de férias...",
            category="politicas",
            rh_user_id="rh_001",
            user_type="rh"
        )
    """
    
    if user_type != "rh":
        logger.warning("🚫 Acesso negado para user_type=%s", user_type)
        return {
            "success": False,
            "error": "Acesso negado: apenas usuários RH podem atualizar a base"
        }
    
    index_name = ElasticsearchConstants.POLITICAS_BASE_INDEX
    
    try:
        if action == "remove":
            logger.debug("🗑️  Removendo documento: %s", document_title)
            
            query = {
                "query": {
                    "match": {
                        "title": document_title
                    }
                }
            }
            response = es_client.delete_by_query(index=index_name, body=query)
            
            logger.info(
                "🗑️  Documento removido: %s | Deletados: %d",
                document_title,
                response.get("deleted", 0)
            )
            
            return {
                "success": True,
                "action": "remove",
                "document_title": document_title,
                "deleted_count": response.get("deleted", 0),
                "timestamp": datetime.now().isoformat()
            }
        
        elif action in ["add", "update"]:
            logger.debug("📝 %s documento: %s", "Adicionando" if action == "add" else "Atualizando", document_title)
            
            embedding = generate_embedding(content)
            doc_id = document_title.lower().replace(" ", "_")
            
            document = {
                "title": document_title,
                "content": content,
                "category": category,
                "embedding": embedding,
                "last_updated": datetime.now().isoformat(),
                "updated_by": rh_user_id,
                "department": "RH",
                "tags": [category, "onboarding"],
            }
            
            if action == "update":
                logger.debug("🔄 Atualizando documento no ES")
                es_client.update(
                    index=index_name,
                    id=doc_id,
                    body={"doc": document, "doc_as_upsert": True}
                )
            else:
                logger.debug("➕ Adicionando novo documento ao ES")
                es_client.index(
                    index=index_name,
                    id=doc_id,
                    document=document
                )
            
            logger.info(
                "✅ Documento %s: %s | Categoria: %s | Por: %s",
                action.upper(),
                document_title,
                category,
                rh_user_id
            )
            
            return {
                "success": True,
                "action": action,
                "document_id": doc_id,
                "document_title": document_title,
                "category": category,
                "timestamp": datetime.now().isoformat(),
                "updated_by": rh_user_id
            }
        
        else:
            logger.warning("❌ Ação inválida: %s", action)
            return {
                "success": False,
                "error": f"Ação inválida: {action}"
            }
    
    except Exception as e:
        logger.error(
            "❌ Erro ao atualizar base: %s\n%s",
            str(e),
            traceback.format_exc()
        )
        return {
            "success": False,
            "error": f"Erro ao atualizar base: {str(e)}"
        }


# ==============================================================
# TOOL 4: CHECK_ONBOARDING_STATUS (Consultar progresso)
# ==============================================================


@log_tool_execution  # ✅ NOVO: Decorator
async def check_onboarding_status(user_id: str) -> Dict[str, Any]:
    """
    ✅ Consulta o progresso do onboarding LÊ DADOS DO MESMO JSON (SIMPLIFICADO PARA TESTES).
    
    Args:
        user_id: ID do funcionário
    
    Returns:
        Dict com nome, progresso, etapas completas e pendentes
        
    Etapas monitoradas (do mesmo JSON):
        1. dados_pessoais (nome_completo, cpf, data_nascimento, cargo)
        2. contato (forma_pagamento: pix ou deposito)
        3. documentos (cpf)
        
    Exemplo:
        result = await check_onboarding_status("session-123")
        print(f"Funcionário: {result['nome_completo']}")
        print(f"Progresso: {result['progress_percentage']}%")
        print(f"Etapas pendentes: {result['pending_steps']}")
    """
    
    try:
        employee_file = EMPLOYEES_DATA_DIR / f"{user_id}.json"
        
        if not employee_file.exists():
            logger.warning("❌ Funcionário não encontrado: %s", user_id)
            return {
                "success": False,
                "error": f"Funcionário {user_id} não encontrado"
            }
        
        logger.debug("📂 Carregando status de %s", user_id)
        
        with open(employee_file, 'r', encoding='utf-8') as f:
            employee_data = json.load(f)
        
        # ✅ Extrai nome do JSON
        nome_completo = employee_data.get("nome_completo", "Sem nome")
        
        # ✅ Verifica cada etapa (DO MESMO JSON)
        completed_steps = []
        pending_steps = []
        
        # Etapa 1: Dados pessoais
        if employee_data.get("dados_pessoais"):
            completed_steps.append("dados_pessoais")
        else:
            pending_steps.append("dados_pessoais")
        
        # Etapa 2: Forma de pagamento
        if employee_data.get("contato", {}).get("forma_pagamento"):
            completed_steps.append("forma_pagamento")
        else:
            pending_steps.append("forma_pagamento")
        
        # Etapa 3: Documento CPF
        if any(d.get("tipo") == "cpf" for d in employee_data.get("documentos", [])):
            completed_steps.append("cpf_documento")
        else:
            pending_steps.append("cpf_documento")
        
        progresso = employee_data.get("onboarding_status", {}).get("progresso", 0)
        next_action = pending_steps[0] if pending_steps else "Onboarding completo"
        
        logger.info(
            "📊 [%s - %s] Progresso: %d%% | Pendentes: %d",
            user_id,
            nome_completo,
            progresso,
            len(pending_steps)
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "nome_completo": nome_completo,  # ✅ NOVO: Nome no resultado
            "progress_percentage": progresso,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "next_action": f"Enviar {next_action}" if next_action != "Onboarding completo" else next_action,
            "estimated_completion": f"{len(pending_steps)} etapas restantes",
            "last_activity": employee_data.get("updated_at")
        }
    
    except Exception as e:
        logger.error(
            "❌ Erro ao consultar status de %s: %s",
            user_id,
            str(e)
        )
        return {
            "success": False,
            "error": f"Erro ao consultar status: {str(e)}"
        }


# ==============================================================
# REGISTRO DAS TOOLS NO AUTOGEN 0.4
# ==============================================================


search_knowledge_base_tool = FunctionTool(
    name="search_knowledge_base",
    description="Busca semântica na base de conhecimento (RAG). Use para responder dúvidas sobre a empresa.",
    func=search_knowledge_base,
)
search_politicas_base_tool = FunctionTool(
    name="search_politicas_base",
    description="Busca semântica na base de conhecimento (RAG). Use para responder dúvidas beneficios e políticas internas da empresa.",
    func=search_politicas_base,
)


store_employee_data_tool = FunctionTool(
    name="store_employee_data",
    description="Armazena dados do funcionário em JSON local. Use após coletar dados pessoais, contato ou documentos. Calcula progresso automaticamente.",
    func=store_employee_data,
)


update_knowledge_base_tool = FunctionTool(
    name="update_knowledge_base",
    description="Atualiza base de conhecimento (APENAS RH). Permite adicionar, atualizar ou remover políticas da empresa no Elasticsearch.",
    func=update_knowledge_base,
)


check_onboarding_status_tool = FunctionTool(
    name="check_onboarding_status",
    description="Consulta progresso do onboarding de um funcionário. Retorna nome, etapas completas, pendentes e próxima ação.",
    func=check_onboarding_status,
)


# ==============================================================
# LISTA PARA REGISTRO EM AGENT_BUILDER
# ==============================================================


TOOLS_LIST = [
    search_knowledge_base_tool,
    search_politicas_base_tool,
    store_employee_data_tool,
    update_knowledge_base_tool,
    check_onboarding_status_tool,
]
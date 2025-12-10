import os
import json
import base64
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

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
# EMBEDDING
# ==============================================================

def generate_embedding(text: str) -> List[float]:
    try:
        resp = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        raise


# ==============================================================
# TOOL 1: SEARCH_KNOWLEDGE_BASE (RAG)
# ==============================================================

async def search_knowledge_base(
    query: str,
    base_type: str = "neuro",
    top_k: int = 3,
    user_type: str = "funcionario"
) -> Dict[str, Any]:
    """
    Busca semântica na base de conhecimento usando Elasticsearch.
    
    Args:
        query: Pergunta do usuário
        base_type: "neuro" ou "politicas"
        top_k: Número de resultados
        user_type: "funcionario" ou "rh"
    
    Returns:
        Dict com sucesso, query e resultados
    """
    
    INDEX_MAP = {
        "neuro": ElasticsearchConstants.NEURO_BASE_INDEX,
        "politicas": ElasticsearchConstants.POLITICAS_BASE_INDEX,
    }
    
    if base_type not in INDEX_MAP:
        return {
            "success": False,
            "error": f"base_type inválido: {base_type}",
        }
    
    index_name = INDEX_MAP[base_type]
    
    try:
        embedding = generate_embedding(query)
    except:
        return {
            "success": False,
            "error": "Erro ao gerar embedding"
        }
    
    try:
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


async def store_employee_data(
    user_id: str,
    data_type: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Armazena dados do funcionário em arquivo JSON local.
    
    Args:
        user_id: ID único do funcionário
        data_type: "dados_pessoais", "contato", "dados_bancarios", "documento"
        data: Dict com os dados a salvar
    
    Returns:
        Dict com sucesso e caminho do arquivo
    """
    
    try:
        employee_file = EMPLOYEES_DATA_DIR / f"{user_id}.json"
        
        if employee_file.exists():
            with open(employee_file, 'r', encoding='utf-8') as f:
                employee_data = json.load(f)
        else:
            employee_data = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "dados_pessoais": {},
                "contato": {},
                "dados_bancarios": {},
                "documentos": [],
                "onboarding_status": {
                    "progresso": 0,
                    "status": "em_andamento"
                }
            }
        
        if data_type == "documento":
            employee_data["documentos"].append({
                **data,
                "timestamp": datetime.now().isoformat()
            })
        elif data_type in ["dados_pessoais", "contato", "dados_bancarios"]:
            employee_data[data_type].update(data)
        else:
            employee_data[data_type] = data
        
        employee_data["updated_at"] = datetime.now().isoformat()
        
        total_steps = 8
        completed = 0
        if employee_data["dados_pessoais"]:
            completed += 1
        if employee_data["contato"].get("email"):
            completed += 1
        if employee_data["contato"].get("telefone"):
            completed += 1
        if employee_data["dados_bancarios"]:
            completed += 1
        
        doc_types_needed = ["rg", "cpf", "ctps", "comprovante_residencia"]
        for doc_type in doc_types_needed:
            if any(d.get("tipo") == doc_type for d in employee_data["documentos"]):
                completed += 1
        
        progresso = int((completed / total_steps) * 100)
        employee_data["onboarding_status"]["progresso"] = progresso
        
        if progresso >= 90:
            employee_data["onboarding_status"]["status"] = "completo"
        
        with open(employee_file, 'w', encoding='utf-8') as f:
            json.dump(employee_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Dados salvos para {user_id} - Progresso: {progresso}%")
        
        return {
            "success": True,
            "user_id": user_id,
            "data_type": data_type,
            "file_path": str(employee_file),
            "progresso": progresso,
            "status": employee_data["onboarding_status"]["status"],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Erro ao salvar dados: {str(e)}"
        }


# ==============================================================
# TOOL 4: UPDATE_KNOWLEDGE_BASE (RH atualiza políticas)
# ==============================================================

async def update_knowledge_base(
    action: str,
    document_title: str,
    content: str = "",
    category: str = "politicas",
    rh_user_id: str = "",
    user_type: str = "rh"
) -> Dict[str, Any]:
    """
    Atualiza base de conhecimento no Elasticsearch (apenas RH).
    
    Args:
        action: "add", "update", "remove"
        document_title: Título do documento
        content: Conteúdo do documento
        category: Categoria (politicas, beneficios, procedimentos)
        rh_user_id: ID do usuário RH
        user_type: Deve ser "rh"
    
    Returns:
        Dict com sucesso e detalhes da operação
    """
    
    if user_type != "rh":
        return {
            "success": False,
            "error": "Acesso negado: apenas usuários RH podem atualizar a base"
        }
    
    index_name = ElasticsearchConstants.POLITICAS_BASE_INDEX
    
    try:
        if action == "remove":
            query = {
                "query": {
                    "match": {
                        "title": document_title
                    }
                }
            }
            response = es_client.delete_by_query(index=index_name, body=query)
            
            return {
                "success": True,
                "action": "remove",
                "document_title": document_title,
                "deleted_count": response.get("deleted", 0),
                "timestamp": datetime.now().isoformat()
            }
        
        elif action in ["add", "update"]:
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
                es_client.update(
                    index=index_name,
                    id=doc_id,
                    body={"doc": document, "doc_as_upsert": True}
                )
            else:
                es_client.index(
                    index=index_name,
                    id=doc_id,
                    document=document
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
            return {
                "success": False,
                "error": f"Ação inválida: {action}"
            }
            
    except Exception as e:
        logger.error(f"Erro ao atualizar base: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Erro ao atualizar base: {str(e)}"
        }


# ==============================================================
# TOOL 5: CHECK_ONBOARDING_STATUS (Consultar progresso)
# ==============================================================

async def check_onboarding_status(
    user_id: str
) -> Dict[str, Any]:
    """
    Consulta o progresso do onboarding de um funcionário.
    
    Args:
        user_id: ID do funcionário
    
    Returns:
        Dict com progresso, etapas completas e pendentes
    """
    
    try:
        employee_file = EMPLOYEES_DATA_DIR / f"{user_id}.json"
        
        if not employee_file.exists():
            return {
                "success": False,
                "error": f"Funcionário {user_id} não encontrado"
            }
        
        with open(employee_file, 'r', encoding='utf-8') as f:
            employee_data = json.load(f)
        
        completed_steps = []
        pending_steps = []
        
        if employee_data.get("dados_pessoais"):
            completed_steps.append("dados_pessoais")
        else:
            pending_steps.append("dados_pessoais")
        
        if employee_data.get("contato", {}).get("email"):
            completed_steps.append("email")
        else:
            pending_steps.append("email")
        
        if employee_data.get("contato", {}).get("telefone"):
            completed_steps.append("telefone")
        else:
            pending_steps.append("telefone")
        
        if employee_data.get("dados_bancarios"):
            completed_steps.append("dados_bancarios")
        else:
            pending_steps.append("dados_bancarios")
        
        doc_types = ["rg", "cpf", "ctps", "comprovante_residencia"]
        for doc_type in doc_types:
            if any(d.get("tipo") == doc_type for d in employee_data.get("documentos", [])):
                completed_steps.append(doc_type)
            else:
                pending_steps.append(doc_type)
        
        progresso = employee_data.get("onboarding_status", {}).get("progresso", 0)
        
        next_action = pending_steps[0] if pending_steps else "Onboarding completo"
        
        return {
            "success": True,
            "user_id": user_id,
            "progress_percentage": progresso,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "next_action": f"Enviar {next_action}" if next_action != "Onboarding completo" else next_action,
            "estimated_completion": f"{len(pending_steps)} etapas restantes",
            "last_activity": employee_data.get("updated_at")
        }
        
    except Exception as e:
        logger.error(f"Erro ao consultar status: {e}")
        return {
            "success": False,
            "error": f"Erro ao consultar status: {str(e)}"
        }


# ==============================================================
# REGISTRO DAS TOOLS NO AUTOGEN 0.4
# ==============================================================

search_knowledge_base_tool = FunctionTool(
    name="search_knowledge_base",
    description="Busca semântica na base de conhecimento (RAG). Use para responder dúvidas sobre benefícios, políticas e procedimentos da empresa.",
    func=search_knowledge_base,
)


store_employee_data_tool = FunctionTool(
    name="store_employee_data",
    description="Armazena dados do funcionário em JSON local. Use após coletar dados pessoais, contato ou bancários. Calcula progresso automaticamente.",
    func=store_employee_data,
)

update_knowledge_base_tool = FunctionTool(
    name="update_knowledge_base",
    description="Atualiza base de conhecimento (APENAS RH). Permite adicionar, atualizar ou remover políticas da empresa no Elasticsearch.",
    func=update_knowledge_base,
)

check_onboarding_status_tool = FunctionTool(
    name="check_onboarding_status",
    description="Consulta progresso do onboarding de um funcionário. Retorna etapas completas, pendentes e próxima ação.",
    func=check_onboarding_status,
)
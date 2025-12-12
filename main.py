
import os
import yaml
import asyncio
import json
import uvicorn
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from redis import Redis as SyncRedis
from dotenv import load_dotenv

load_dotenv()

from app.configs import config
from app.configs.logging_config import configurar_logger
from app.services.queue_manager import QueueManager
from app.utils.openai_utils import test_openai_connection
from app.services.orchestrator_registry import get_orchestrator, set_orchestrator, remove_orchestrator
from app.services.ai_orchestrator import AiOrchestrator
import tasks

logger = configurar_logger(__name__)
API_KEY = os.getenv("OPENAI_API_KEY", "")

queue_manager = QueueManager()
sync_redis = SyncRedis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

prompts_fpath = config.PathSystemPrompts.PROMPTS_PATH
if not prompts_fpath.exists():
    raise FileNotFoundError(f"Arquivo de prompts não encontrado em: {prompts_fpath}")
with open(prompts_fpath, "r", encoding="utf-8") as file:
    prompts = yaml.safe_load(file)

rules_fpath = config.PathSystemPrompts.RULES_PATH
if not rules_fpath.exists():
    raise FileNotFoundError(f"Arquivo de rules não encontrado em: {rules_fpath}")
with open(rules_fpath, "r", encoding="utf-8") as file:
    rules = yaml.safe_load(file)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(tasks.reply_loop(queue_manager))
    yield
    logger.info("Finalizando aplicação")

app = FastAPI(
    title="Sistema de Onboarding - API",
    description="API para gerenciamento de onboarding de funcionários",
    version="1.0.0",
    lifespan=lifespan
)

class OnboardingMessage(BaseModel):
    msg: str
    phone: str
    rid: str
    employee_name: Optional[str] = ""

@app.get("/api/health/openai")
async def health_check_openai():
    try:
        if test_openai_connection():
            return {
                "status": "healthy",
                "service": "OpenAI",
                "message": "Conexão com OpenAI está funcionando corretamente"
            }
        else:
            raise HTTPException(status_code=503, detail="Falha na conexão com OpenAI")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao testar conexão: {str(e)}")

@app.post("/api/onboarding/message")
async def handle_onboarding_message(
    message: OnboardingMessage,
    x_user_type: str = Header()
):
    """
    ✅ CORRIGIDO: Enfileira mensagens AQUI em main.py
    
    Fluxo:
    1. Executa orchestrator
    2. Recebe resultado (pode ter múltiplas mensagens)
    3. Enfileira CADA mensagem
    4. Aguarda reply_loop processar
    5. Cleanup
    """
    logger.info(f"Recebido: {message.model_dump()}")
    logger.info(f"Tipo de usuário: {x_user_type}")
    
    session_id = message.rid
    chat_key = f"chat:{session_id}"

    # ✅ Cria event ANTES de tudo
    processed_event = queue_manager.create_processed_event(chat_key)

    orchestrator = get_orchestrator(chat_key)
    if not orchestrator:
        orchestrator = AiOrchestrator(
            session_id=session_id,
            chat_key=chat_key,
            user_type=x_user_type,  # ← AQUI! Recebe o tipo de usuário
            openai_api_key=API_KEY,
            queue_manager=queue_manager,
            phone=message.phone
        )
        await orchestrator.prepare()
        set_orchestrator(chat_key, orchestrator)

    talker_messages = []

    try:
        # ✅ Executa fluxo
        result = await orchestrator.execute(
            first_message=message.msg,
            employee_name=message.employee_name or ""
        )
        
        # ✅ NOVO: Enfileira resultado AQUI (se houver)
        if result:
            result_str = str(result) if not isinstance(result, str) else result
            talker_messages.append(result_str)
            
            logger.debug(
                f"[{chat_key}] 📤 Preparando enfileiramento | Len: {len(result_str)}"
            )
            
            # ✅ Cria mensagem para fila
            outcome_message = json.dumps({
                "phone": message.phone,
                "msg": result_str,
                "chat_key": chat_key,
                "audio": False
            })
            
            # ✅ Enfileira em queue_manager
            await queue_manager.post_to_global_outcome_queue(outcome_message)
            logger.info(f"[{chat_key}] ✅ Mensagem enfileirada em main.py | Len: {len(result_str)}")
        
        # ✅ Se conversa acabou, faz cleanup
        if orchestrator.conversation_manager.is_conversation_finished():
            logger.info(f"[{chat_key}] 🏁 Conversa finalizada, aguardando processamento...")
            
            try:
                # ✅ Aguarda reply_loop processar a fila (timeout 5s)
                await asyncio.wait_for(processed_event.wait(), timeout=5.0)
                logger.info(f"[{chat_key}] ✅ Reply_loop processou, limpando...")
            except asyncio.TimeoutError:
                logger.warning(f"[{chat_key}] ⚠️  Timeout esperando reply_loop, continuando cleanup")
            
            # ✅ Cleanup
            await orchestrator.cleanup()
            remove_orchestrator(chat_key)
            logger.info(f"[{chat_key}] ✅ Orchestrator removido, sessão finalizada")

        return {
            "session_id": session_id,
            "response": talker_messages
        }

    except Exception as e:
        logger.error(f"[{chat_key}] ❌ Erro:\n{traceback.format_exc()}")
        
        # ✅ Limpa em caso de erro
        try:
            remove_orchestrator(chat_key)
        except:
            pass
        
        raise HTTPException(
            status_code=500,
            detail="Erro interno no onboarding"
        )

def main():
    logger.info("Inicializando aplicação FastAPI")
    try:
        if not test_openai_connection():
            logger.warning("A aplicação iniciará mesmo com falha na OpenAI")
    except:
        logger.warning("Falha no teste da OpenAI")
    try:
        sync_redis.ping()
        logger.info("Redis conectado!")
    except Exception as e:
        raise ConnectionError(f"Redis error: {e}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 7000)),
        reload=False,
        workers=1
    )

if __name__ == "__main__":
    main()
import os
import yaml
import asyncio
import json
import uvicorn
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
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
    # ✅ Iniciar apenas o reply_loop, sem teste de GraphFlow
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
async def handle_onboarding_message(message: OnboardingMessage):
    session_id = message.rid
    chat_key = f"chat:{session_id}"

    # Recupera ou cria um orchestrator para essa conversa
    orchestrator = get_orchestrator(chat_key)
    if not orchestrator:
        orchestrator = AiOrchestrator(
            session_id=session_id,
            chat_key=chat_key,
            user_type="",
            openai_api_key=API_KEY,
            queue_manager=queue_manager,
            phone=message.phone
        )
        await orchestrator.prepare()
        set_orchestrator(chat_key, orchestrator)

    talker_messages = []

    try:
        # Consome o generator de forma assíncrona
        async for msg in orchestrator.execute(
            first_message=message.msg,
            employee_name=message.employee_name or ""
        ):
            # msg é uma string (mensagem do Talker)
            # Filtra apenas mensagens reais (não MemoryContent ou outras estruturas)
            if isinstance(msg, str) and not msg.startswith("[MemoryContent"):
                talker_messages.append(msg)
                
                # Posta na fila global para tasks.py processar
                outcome_message = json.dumps({
                    "phone": message.phone,
                    "msg": msg,
                    "chat_key": chat_key,
                    "audio": False
                })
                await queue_manager.post_to_global_outcome_queue(outcome_message)

        # Finaliza a conversa se necessário
        if orchestrator.conversation_manager.is_conversation_finished():
            await orchestrator.cleanup()
            remove_orchestrator(chat_key)

        return {
            "session_id": session_id,
            "response": talker_messages
        }

    except Exception:
        logger.error(f"[{chat_key}] Erro:\n{traceback.format_exc()}")
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

import json
import traceback
import requests
import asyncio
from datetime import datetime
from typing import Dict, Any

from app.configs import config
from app.services.queue_manager import QueueManager, ChatState
from app.services.ai_orchestrator import AiOrchestrator
from app.configs.logging_config import configurar_logger

logger = configurar_logger(__name__)

queue_manager = QueueManager()

###############################################################################
# LOOP PRINCIPAL DE CONVERSA (COM AI_ORCHESTRATOR)
###############################################################################

async def conversation_loop(
    session_id: str,
    chat_key: str,
    phone: str,
    prompts: dict,
    rules: dict,
    first_user_message: str,
    employee_name: str = ""
):
    """
    Executa o AiOrchestrator completamente
    """
    logger.info(f"[{chat_key}] ▶️ Iniciando loop de conversa com AI...")

    orchestrator = None
    try:
        # 1. CRIAR ORQUESTRADOR (sem user_type)
        orchestrator = AiOrchestrator(
            session_id=session_id,
            chat_key=chat_key,
            openai_api_key=config.OpenAI.API_KEY,
            queue_manager=queue_manager,
        )

        # 2. PREPARAR AGENTES E GRAPHFLOW
        logger.info(f"[{chat_key}] ⚙️ Preparando agentes e GraphFlow...")
        await orchestrator.prepare()

        # 3. EXECUTAR FLUXO
        logger.info(f"[{chat_key}] 🚀 Executando fluxo de onboarding...")
        result = await orchestrator.execute(
            first_message=first_user_message,
            employee_name=employee_name
        )

        # 4. PROCESSAR RESULTADO
        logger.info(f"[{chat_key}] ✅ Fluxo concluído com sucesso")
        logger.debug(f"[{chat_key}] Resultado: {result}")

        # 5. ENVIAR RESPOSTA AO USUÁRIO
        if result and result.get("finalization_data"):
            final_message = result["finalization_data"].get(
                "conteudo", {}
            ).get("mensagem_final", "Onboarding concluído com sucesso!")

            out_msg_str = json.dumps({
                "phone": phone,
                "msg": final_message,
                "chat_key": chat_key,
                "audio": False
            })
            await queue_manager.post_to_global_outcome_queue(out_msg_str)
            logger.info(f"[{chat_key}] 📤 Resposta final enviada ao usuário")

        # Marcar conversa como finalizada
        await queue_manager.set_chat_status(chat_key, ChatState.CONVERSATION_ENDED)

    except Exception as e:
        error_str = traceback.format_exc()
        logger.error(f"[{chat_key}] ❌ ERRO crítico no loop de conversa:")
        logger.error(f"[{chat_key}] {error_str}")

        # Registrar erro no Redis
        await queue_manager.set_chat_status(chat_key, ChatState.CONVERSATION_ENDED)
        await queue_manager.append_error(chat_key, error_str)

        # Notificar usuário sobre erro
        error_msg = "Desculpe, ocorreu um erro ao processar seu onboarding. Tente novamente."
        out_msg_str = json.dumps({
            "phone": phone,
            "msg": error_msg,
            "chat_key": chat_key,
            "audio": False
        })
        try:
            await queue_manager.post_to_global_outcome_queue(out_msg_str)
        except:
            logger.error(f"[{chat_key}] Falha ao enviar mensagem de erro ao usuário")

    finally:
        # 6. CLEANUP
        if orchestrator:
            try:
                await orchestrator.cleanup()
                logger.info(f"[{chat_key}] 🧹 Recursos do Orchestrator finalizados")
            except Exception as e:
                logger.error(f"[{chat_key}] Erro no cleanup: {e}")

        await queue_manager.end_chat(chat_key)
        logger.info(f"[{chat_key}] 🏁 Loop de conversa finalizado")


###############################################################################
# LOOP DE RESPOSTA
###############################################################################

async def reply_loop(queue_manager: QueueManager):
    logger.debug("🔄 Iniciando reply_loop")
    logger.info("✅ reply_loop pronto para enviar mensagens")

    while True:
        try:
            next_message = await queue_manager.blpop_from_global_outcome_queue(timeout=60)
            if next_message is None:
                logger.debug("⏰ Timeout na fila global (aguardando mensagens...)")
                continue

            try:
                message_dict = json.loads(next_message)
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON inválido na fila: {e}")
                continue

            phone = message_dict.get("phone")
            agent_message = message_dict.get("msg")
            chat_key = message_dict.get("chat_key", "unknown")
            audio = message_dict.get("audio", False)

            if not phone or not agent_message:
                logger.warning(f"[{chat_key}] ⚠️ Mensagem incompleta: faltam campos")
                continue

            logger.info(f"[{chat_key}] 📤 Enviando para Hyperflow: {agent_message[:80]}...")

            try:
                result = requests.post(
                    config.ServerConstants.HYPERFLOW_URL,
                    json={"audio": audio, "phone": phone, "msg": agent_message},
                    headers={"client_id": config.ServerConstants.HYPERFLOW_API_KEY},
                    timeout=config.ServerConstants.HYPERFLOW_TIMEOUT
                )

                if result.status_code != 200:
                    logger.error(f"[{chat_key}] ❌ Hyperflow error: {result.status_code} - {result.text[:200]}")
                else:
                    logger.info(f"[{chat_key}] ✅ Mensagem enviada via Hyperflow")

            except requests.exceptions.RequestException as e:
                logger.error(f"[{chat_key}] ❌ Falha ao enviar para Hyperflow: {e}")

            await queue_manager.set_chat_status(chat_key, ChatState.WAITING_USER_RESPONSE)

        except Exception as e:
            logger.error(f"❌ Erro no reply_loop: {traceback.format_exc()}")
            await asyncio.sleep(5)


###############################################################################
# POSTAGEM DE MENSAGENS INICIAIS
###############################################################################

async def post_first_messages(
    chat_key: str,
    phone: str,
    delay: int,
    session_id: str,
    first_user_message: str,
    prompts,
    rules,
    employee_name: str = ""
):
    logger.info(f"[{chat_key}] ⏳ Aguardando {delay}s para agrupar mensagens iniciais...")
    await asyncio.sleep(delay)

    message_list = await queue_manager.dequeue_input_buffer(chat_key)
    final_first_message = "\n".join(message_list) or first_user_message
    logger.info(f"[{chat_key}] 📥 Buffer contém {len(message_list)} mensagens")

    # Iniciar conversation_loop em background
    asyncio.create_task(
        conversation_loop(
            session_id=session_id,
            chat_key=chat_key,
            phone=phone,
            prompts=prompts,
            rules=rules,
            first_user_message=final_first_message,
            employee_name=employee_name
        )
    )

    await queue_manager.set_chat_status(chat_key, ChatState.WAITING_AGENT_RESPONSE)
    logger.info(f"[{chat_key}] ✅ Agente iniciado em background")


###############################################################################
# POSTAGEM DE MENSAGENS SUBSEQUENTES
###############################################################################

async def post_income_messages(
    redis_key: str,
    delay: int,
    employee_name: str = ""
):
    logger.info(f"[{redis_key}] ⏳ Aguardando {delay}s para agrupar mensagens...")
    await asyncio.sleep(delay)

    message_list = await queue_manager.dequeue_input_buffer(redis_key)
    if not message_list:
        logger.warning(f"[{redis_key}] ⚠️ Buffer vazio após delay")
        return

    final_message = "\n".join(message_list)
    logger.info(f"[{redis_key}] 📥 Enviando {len(message_list)} mensagens ao agente")

    await queue_manager.post_message_to_agent(
        redis_key,
        f"Employee: {employee_name}\n{final_message}",
        agent="coordinator"
    )
    await queue_manager.set_chat_status(redis_key, ChatState.WAITING_AGENT_RESPONSE)


###############################################################################
# FOLLOW-UP AUTOMÁTICO
###############################################################################

async def follow_up_and_terminate(chat_key: str, phone: str):
    FOLLOW_UP_DELAY = 10 * 60  # 10 minutos
    logger.info(f"[{chat_key}] ⏳ Follow-up agendado em {FOLLOW_UP_DELAY}s")
    await asyncio.sleep(FOLLOW_UP_DELAY)

    current_status = await queue_manager.get_chat_status(chat_key)
    if current_status == ChatState.CONVERSATION_ENDED:
        logger.info(f"[{chat_key}] Conversa já encerrada")
        return

    # Enviar follow-up
    follow_up_msg = "Olá! Ainda estou por aqui. Alguma dúvida?"
    out_msg = json.dumps({
        "phone": phone,
        "msg": follow_up_msg,
        "chat_key": chat_key,
        "audio": False
    })
    await queue_manager.post_to_global_outcome_queue(out_msg)
    logger.info(f"[{chat_key}] 📤 Follow-up enviado")

    # Aguardar 30s mais
    await asyncio.sleep(30)
    current_status = await queue_manager.get_chat_status(chat_key)
    if current_status == ChatState.WAITING_USER_RESPONSE:
        closing_msg = json.dumps({
            "phone": phone,
            "msg": "Conversa encerrada por inatividade. Obrigado!",
            "chat_key": chat_key,
            "audio": False
        })
        await queue_manager.post_to_global_outcome_queue(closing_msg)
        await queue_manager.end_chat(chat_key)
        await queue_manager.set_chat_status(chat_key, ChatState.CONVERSATION_ENDED)


###############################################################################
# LIMPEZA PERIÓDICA
###############################################################################

async def cleanup_expired_chats(max_age_hours: int = 168):
    logger.info(f"🧹 Limpeza de chats com mais de {max_age_hours}h")
    try:
        all_chat_keys = await queue_manager.get_all_chat_keys()
        cleaned = 0
        for chat_key in all_chat_keys:
            last_activity = await queue_manager.get_last_activity(chat_key)
            if last_activity:
                hours_inactive = (datetime.now().timestamp() - last_activity) / 3600
                if hours_inactive > max_age_hours:
                    await queue_manager.delete_chat(chat_key)
                    cleaned += 1
        logger.info(f"✅ Limpeza: {cleaned} chats removidos")
    except Exception as e:
        logger.error(f"❌ Erro na limpeza: {e}")

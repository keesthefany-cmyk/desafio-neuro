from enum import Enum
from typing import List, Optional, Dict, Any
import json
import time
import asyncio

import redis.asyncio as aioredis


from app.configs.logging_config import configurar_logger
from app.configs.config import config
logger = configurar_logger("queue_manager")


class ChatState(str, Enum):
    WAITING_USER_RESPONSE = "waiting_user_response"
    WAITING_AGENT_RESPONSE = "waiting_agent_response"
    CONVERSATION_ENDED = "conversation_ended"
    ACC_USER_INPUT = "accumulating_user_input"
    ACC_FIRST_INTERACTION = "accumulating_first_interaction"


class QueueManager:
    """
    Gerencia filas Redis usadas pelo sistema.
    Remove totalmente o campo user_type, pois não é mais usado.
    """

    __KEY_STATUS = "status"
    __KEY_INPUT_BUFFER = "input_buffer"
    __KEY_INCOME_MESSAGES = "income_messages"
    __KEY_GLOBAL_OUTCOME_QUEUE = "global_outcome_queue"
    __KEY_LAST_ACTIVITY = "last_activity"
    KEY_ERROR = "errors"

   
    def __init__(self):
        try:
            # Conecta no Redis usando URL do config
            self.redis = aioredis.from_url(
                config.redis.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"✅ Conectado ao Redis: {config.redis.REDIS_URL}")
        except Exception as e:
            logger.error(f"❌ Error connecting to Redis: {e}")
            raise

    # -------------------------
    # KEYS
    # -------------------------
    @staticmethod
    def _mk_status_key(chat_key: str) -> str:
        return f"{chat_key}:{QueueManager.__KEY_STATUS}"

    @staticmethod
    def _mk_input_buffer_key(chat_key: str) -> str:
        return f"{chat_key}:{QueueManager.__KEY_INPUT_BUFFER}"

    @staticmethod
    def _mk_income_messages_key(chat_key: str) -> str:
        return f"{chat_key}:{QueueManager.__KEY_INCOME_MESSAGES}"

    @staticmethod
    def _mk_last_activity_key(chat_key: str) -> str:
        return f"{chat_key}:{QueueManager.__KEY_LAST_ACTIVITY}"

    # -------------------------
    # Chat lifecycle
    # -------------------------
    async def chat_exists(self, chat_key: str) -> bool:
        return await self.redis.exists(self._mk_status_key(chat_key)) != 0

    async def set_chat_status(self, chat_key: str, status: ChatState) -> None:
        await self.redis.set(self._mk_status_key(chat_key), status.value)
        await self._touch_last_activity(chat_key)

    async def get_chat_status(self, chat_key: str) -> Optional[ChatState]:
        s = await self.redis.get(self._mk_status_key(chat_key))
        if s is None:
            return None
        try:
            return ChatState(s)
        except ValueError:
            return None

    # -------------------------
    # Input buffer
    # -------------------------
    async def post_to_input_buffer(self, chat_key: str, message: str) -> None:
        await self.redis.rpush(self._mk_input_buffer_key(chat_key), message)
        await self._touch_last_activity(chat_key)

    async def dequeue_input_buffer(self, chat_key: str) -> List[str]:
        msgs: List[str] = []
        while True:
            m = await self.redis.lpop(self._mk_input_buffer_key(chat_key))
            if m is None:
                break
            msgs.append(m)
        if msgs:
            await self._touch_last_activity(chat_key)
        return msgs

    # -------------------------
    # Income messages
    # -------------------------
    async def post_message_to_agent(
        self,
        chat_key: str,
        message: str,
        agent: str = "coordinator",
        rid: str = "",
        phone: str = "",
        employee_name: str = "",
    ) -> None:
        """
        Mensagem para agentes — versão SEM user_type.
        """
        payload = {
            "msg": message,
            "agent": agent,
            "rid": rid,
            "phone": phone,
            "employee_name": employee_name,
            "timestamp": time.time(),
        }

        await self.redis.rpush(
            self._mk_income_messages_key(chat_key),
            json.dumps(payload)
        )

        await self._touch_last_activity(chat_key)
        logger.debug("[%s] Mensagem para '%s' enfileirada", chat_key, agent)

    async def blpop_from_income_messages(self, chat_key: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
        res = await self.redis.blpop([self._mk_income_messages_key(chat_key)], timeout=timeout)
        if not res:
            return None
        _, payload = res
        try:
            return json.loads(payload)
        except Exception:
            logger.exception("Payload inválido em income_messages: %s", payload)
            return None

    # -------------------------
    # Outcome queue
    # -------------------------
    async def post_to_global_outcome_queue(self, message: str) -> None:
        await self.redis.rpush(QueueManager.__KEY_GLOBAL_OUTCOME_QUEUE, message)
        logger.debug("Mensagem postada na fila global")

    async def blpop_from_global_outcome_queue(self, timeout: int = 0) -> Optional[str]:
        res = await self.redis.blpop([QueueManager.__KEY_GLOBAL_OUTCOME_QUEUE], timeout=timeout)
        if not res:
            return None
        return res[1]

    # -------------------------
    # Cleanup
    # -------------------------
    async def end_chat(self, chat_key: str) -> None:
        await self.set_chat_status(chat_key, ChatState.CONVERSATION_ENDED)
        await self.redis.delete(self._mk_income_messages_key(chat_key))
        await self.redis.delete(self._mk_input_buffer_key(chat_key))
        logger.info("[%s] Chat finalizado e limpo", chat_key)

    # -------------------------
    # Errors
    # -------------------------
    async def append_error(self, chat_key: str, error_message: str) -> None:
        await self.redis.rpush(f"{chat_key}:{self.KEY_ERROR}", error_message)
        await self._touch_last_activity(chat_key)

    async def close(self) -> None:
        await self.redis.close()
        try:
            await self.redis.connection_pool.disconnect()
        except Exception:
            pass

    # -------------------------
    # Extra
    # -------------------------
    async def _touch_last_activity(self, chat_key: str) -> None:
        await self.redis.set(self._mk_last_activity_key(chat_key), str(int(time.time())))

    async def get_last_activity(self, chat_key: str) -> Optional[float]:
        v = await self.redis.get(self._mk_last_activity_key(chat_key))
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    async def get_all_chat_keys(self) -> List[str]:
        return await self.redis.keys("chat:*") or []

    async def delete_chat(self, chat_key: str) -> None:
        keys_to_rm = await self.redis.keys(f"{chat_key}:*")
        if keys_to_rm:
            await self.redis.delete(*keys_to_rm)
        logger.debug("[%s] Chat removido do Redis", chat_key)

    async def get_metrics(self, chat_key: str) -> Dict[str, Any]:
        status = await self.get_chat_status(chat_key)
        last_activity = await self.get_last_activity(chat_key)
        return {
            "status": status.value if status else None,
            "last_activity": last_activity,
        }

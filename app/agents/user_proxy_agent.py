import json
from typing import List, Sequence

from autogen_core import CancellationToken
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import ChatMessage, StopMessage, TextMessage

from app.configs.config import ConversationContants
from app.configs.logging_config import configurar_logger
from app.services.queue_manager import QueueManager

logger = configurar_logger(__name__)


class UserProxyAgent(BaseChatAgent):
    def __init__(
        self,
        name: str,
        chat_key: str,
        phone: str,
        termination_string: str,
        description: str,
        queue_manager: QueueManager,
        user_type: str
    ) -> None:
        super().__init__(name, description)
        self.chat_key = chat_key
        self.termination_string = termination_string.lower().strip()
        self.queue_manager = queue_manager
        self.phone = phone
        self.user_type = user_type

    @property
    def produced_message_types(self) -> List[type[ChatMessage]]:
        return [TextMessage, StopMessage]

    async def on_messages(
        self,
        messages: Sequence[ChatMessage],
        cancellation_token: CancellationToken
    ) -> Response:

        last_message = messages[-1]
        content = last_message.content

        logger.info(f"[{self.chat_key}] 📤 Agent → User response")

        # Aqui você DEVOLVE a resposta para o orquestrador
        return Response(
            chat_message=TextMessage(
                content=content,
                source=self.name
            )
        )

    def _should_terminate(self, message_content: str) -> bool:
        return self.termination_string in message_content.lower().strip()

    async def _wait_for_user_input(self) -> Response:
        logger.info(f"[{self.chat_key}] Aguardando nova mensagem do usuário…")

        query_result = await self.queue_manager.blpop_from_income_messages(
            self.chat_key,
            timeout=ConversationContants.CONVERSATION_TIMEOUT
        )

        if query_result is None:
            logger.debug(f"[{self.chat_key}] Timeout → Encerrando agente.")
            await self.on_stop_cleanup()
            return Response(
                chat_message=TextMessage(
                    content="TIMEOUT",
                    source=self.name
                )
            )

        new_message = query_result.get("msg", "")

        if new_message.lower().strip() == "exit":
            logger.debug(f"[{self.chat_key}] Cliente pediu saída.")
            await self.on_stop_cleanup()
            return Response(
                chat_message=StopMessage(
                    content=self.termination_string,
                    source=self.name
                )
            )

        logger.debug(f"[{self.chat_key}] Mensagem recebida: {new_message}")

        chat_msg = TextMessage(
            content=new_message,
            source=self.name,
            metadata={"user_type": self.user_type}
        )

        return Response(chat_message=chat_msg)

    async def on_reset(self, cancellation_token: CancellationToken):
        pass

    async def on_stop_cleanup(self):
        await self.queue_manager.end_chat(self.chat_key)

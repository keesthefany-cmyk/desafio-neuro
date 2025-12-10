import re
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

from autogen_agentchat.messages import BaseChatMessage
from app.services.message_processor import MessageProcessor
from app.configs.logging_config import configurar_logger

logger = configurar_logger(__name__)


class ConversationManager:
    def __init__(
        self,
        session_id: str,
        redis_key: str,
        message_processor: MessageProcessor,
    ):
        self.session_id = session_id
        self.redis_key = redis_key
        self.message_processor = message_processor

        self.conversation_history: List[Dict[str, Any]] = []
        self.finalization_data: Optional[Dict[str, Any]] = None
        self.start_time = datetime.now()

    async def processar_mensagem(self, message: BaseChatMessage) -> None:
        try:
            content_text = self.message_processor.extract_content(message)
            if not content_text:
                return

            source = getattr(message, "source", "unknown")
            filtered = self.message_processor.filter_control_terms(content_text)

            if self._is_valid_agent_source(source):
                self.conversation_history.append({
                    "source": source,
                    "content_raw": content_text,
                    "content_filtered": filtered,
                    "timestamp": datetime.now().isoformat(),
                })

            await self._process_special_messages(source, content_text)

        except Exception as e:
            logger.error(str(e))
            await asyncio.sleep(1)

    def _is_valid_agent_source(self, source: str) -> bool:
        return source in ["user", "Cliente", "talker", "coordinator", "finalizer"]

    async def _process_special_messages(self, source: str, content: str) -> None:
        if source == "finalizer" and "TERMINATE" in content.upper():
            if self.finalization_data is None:
                self._extract_finalization_data(content)

    def _extract_finalization_data(self, content: str) -> None:
        try:
            match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                self.finalization_data = json.loads(match.group(1))
                return

            matches = re.findall(r"\{.*?\}", content, re.DOTALL)
            if matches:
                self.finalization_data = json.loads(matches[-1])
                return

        except Exception:
            self.finalization_data = None

    def is_conversation_finished(self) -> bool:
        return self.finalization_data is not None

    def finalize_conversation(self) -> Dict[str, Any]:
        duration = (datetime.now() - self.start_time).total_seconds()

        return {
            "session_id": self.session_id,
            "status": "finalizado" if self.finalization_data else "incompleto",
            "duration_seconds": round(duration, 2),
            "total_messages": len(self.conversation_history),
            "conversation_history": self.conversation_history,
            "finalization_data": self.finalization_data,
            "sucesso": bool(self.finalization_data),
        }

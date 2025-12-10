from typing import Dict, Optional
from app.services.ai_orchestrator import AiOrchestrator

_ORCHESTRATORS: Dict[str, AiOrchestrator] = {}

def get_orchestrator(chat_key: str) -> Optional[AiOrchestrator]:
    return _ORCHESTRATORS.get(chat_key)

def set_orchestrator(chat_key: str, orchestrator: AiOrchestrator) -> None:
    _ORCHESTRATORS[chat_key] = orchestrator

def remove_orchestrator(chat_key: str) -> None:
    _ORCHESTRATORS.pop(chat_key, None)
import re
import json
from typing import Union, Dict, Any, List
from autogen_agentchat.messages import BaseChatMessage
from app.configs.logging_config import configurar_logger

logger = configurar_logger(__name__)


class MessageProcessor:
    """
    Processador centralizado de mensagens para sistemas multiagente.
    
    Responsabilidades:
    - Extração e validação de conteúdo de BaseChatMessage
    - Filtragem de termos de controle (e.g., TERMINATE, #finalizar)
    - Sanitização e formatação padronizada de mensagens
    - Extração de JSON embutido
    """

    # ✅ CORRIGIDO: Adicionados #finalizar e #finalizado
    CONTROL_TERMS = {
        "TERMINATE", "HANDOFF", "EXIT", "TIMEOUT",
        "STOP", "END", "FINISH", "COMPLETE", 
        "#transbordo", "#finalizar", "#finalizado",
    }

    def __init__(self, redis_key: str):
        self.redis_key = redis_key
        logger.debug(f"[{self.redis_key}] MessageProcessor inicializado")

    def extract_content(self, message: BaseChatMessage) -> str:
        """
        Extrai e retorna o conteúdo textual de uma mensagem.
        
        Se message.content for None ou não for str, retorna string vazia.
        """
        try:
            content = getattr(message, "content", "")
            
            if content is None:
                return ""
            
            if not isinstance(content, str):
                content = str(content)
            
            return content.strip()
        
        except Exception as e:
            logger.error(f"[{self.redis_key}] Erro ao extrair conteúdo: {e}")
            return ""

    def filter_control_terms(self, content: str) -> str:
        """
        Remove, via regex, qualquer ocorrência dos termos de controle.
        
        Exemplo: 'Olá TERMINATE mundo' → 'Olá mundo'
        """
        if not content:
            return content
        
        try:
            pattern = r'\b(' + '|'.join(re.escape(term) for term in self.CONTROL_TERMS) + r')\b'
            filtered = re.sub(pattern, '', content, flags=re.IGNORECASE)
            return re.sub(r'\s+', ' ', filtered).strip()
        
        except Exception as e:
            logger.error(f"[{self.redis_key}] Erro ao filtrar termos de controle: {e}")
            return content

    def sanitize_content(self, content: str) -> str:
        """
        Remove caracteres de controle Unicode e normaliza espaços.
        """
        if not content:
            return content
        
        try:
            # Remove caracteres de controle Unicode
            sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
            # Normaliza espaços múltiplos
            return re.sub(r'\s+', ' ', sanitized).strip()
        
        except Exception as e:
            logger.error(f"[{self.redis_key}] Erro ao sanitizar conteúdo: {e}")
            return content

    def format_message_for_storage(self, message: BaseChatMessage) -> Dict[str, Any]:
        """
        Combina extração, filtragem e sanitização.
        Retorna dicionário pronto para persistência.
        """
        content = self.extract_content(message)
        filtered = self.filter_control_terms(content)
        sanitized = self.sanitize_content(filtered)
        
        return {
            "source": getattr(message, "source", "unknown"),
            "content": sanitized,
            "type": type(message).__name__,
            "has_control_terms": len(filtered) != len(content),
        }

    def extract_json_from_content(self, content: str) -> Union[Dict[str, Any], None]:
        """
        ✅ CORRIGIDO: Extrai bloco JSON delimitado por ```json ... ```
        
        Estratégias:
        1. Bloco ```json...``` (preferido)
        2. {...} no texto
        3. Parsing direto
        
        Retorna o objeto Python decodificado, ou None se não encontrar.
        """
        if not content:
            return None
        
        try:
            # ✅ ESTRATÉGIA 1: Bloco ```json...``` (CORRIGIDO!)
            match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
            
            if match:
                json_block = match.group(1).strip()
                return json.loads(json_block)
            
            # ✅ ESTRATÉGIA 2: {...} em qualquer lugar
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                json_block = match.group(0).strip()
                return json.loads(json_block)
            
            # ✅ ESTRATÉGIA 3: Parsing direto se começar com {
            if content.strip().startswith('{'):
                return json.loads(content.strip())
            
            logger.debug(f"[{self.redis_key}] Nenhum JSON encontrado no conteúdo")
            return None
        
        except json.JSONDecodeError as e:
            logger.debug(f"[{self.redis_key}] JSON inválido: {e}")
            return None
        
        except Exception as e:
            logger.error(f"[{self.redis_key}] Erro ao extrair JSON: {e}")
            return None

    def get_message_statistics(self, messages: List[BaseChatMessage]) -> Dict[str, Any]:
        """
        Retorna estatísticas de mensagens.
        """
        stats = {
            "total_messages": 0,
            "total_characters": 0,
            "messages_with_control_terms": 0,
            "by_source": {},
        }
        
        for msg in messages:
            content = self.extract_content(msg)
            if not content:
                continue
            
            stats["total_messages"] += 1
            stats["total_characters"] += len(content)
            
            if self.filter_control_terms(content) != content:
                stats["messages_with_control_terms"] += 1
            
            src = getattr(msg, "source", "unknown")
            stats["by_source"].setdefault(src, 0)
            stats["by_source"][src] += 1
        
        return stats

    def validate_message(self, message: BaseChatMessage) -> bool:
        """
        Valida se mensagem é processável.
        """
        try:
            content = self.extract_content(message)
            source = getattr(message, "source", None)
            
            return content and source
        
        except Exception as e:
            logger.error(f"[{self.redis_key}] Erro ao validar mensagem: {e}")
            return False
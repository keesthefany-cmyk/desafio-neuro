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
    """
    ✅ GERENCIADOR DE CONVERSA COM SUPORTE A MÚLTIPLOS AGENTES
    
    Responsabilidades:
    - Rastrear histórico de conversa
    - Detectar finalização do onboarding
    - Processar mensagens especiais (coordinator, finalizer)
    - Loggar fluxo completo de conversa
    
    ⚠️  NÃO enfileira mensagens (deixa para main.py)
    """
    
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
        
        logger.info("[%s] 📝 ConversationManager inicializado", self.redis_key)


    async def processar_mensagem(self, message: BaseChatMessage) -> None:
        """
        ✅ CORRIGIDO: Processa mensagem apenas registrando no histórico
        
        Args:
            message: Mensagem do agente (BaseChatMessage)
        
        Fluxo:
        1. Extrai conteúdo de forma segura
        2. Valida agente de origem
        3. Registra no histórico
        4. Se for finalizer: extrai dados de finalização
        
        ✅ IMPORTANTE: NÃO enfileira aqui
            → Enfileiramento acontece em main.py
        """
        try:
            # ✅ Extração segura de conteúdo
            content_text = self.message_processor.extract_content(message)
            if not content_text:
                logger.debug("[%s] ⚠️  Conteúdo vazio extraído", self.redis_key)
                return


            # ✅ Identifica origem
            source = getattr(message, "source", "unknown")
            
            # ✅ Filtra termos de controle
            filtered = self.message_processor.filter_control_terms(content_text)


            # ✅ Valida origem e registra no histórico
            if self._is_valid_agent_source(source):
                content_preview = content_text[:80].replace('\n', ' ')
                
                logger.debug(
                    "[%s] 💾 Registrando mensagem | Source: %s | Preview: %s",
                    self.redis_key,
                    source.upper(),
                    content_preview
                )
                
                self.conversation_history.append({
                    "source": source,
                    "content_raw": content_text,
                    "content_filtered": filtered,
                    "timestamp": datetime.now().isoformat(),
                })


            # ✅ Processa mensagens especiais (apenas finalizer)
            await self._process_special_messages(source, content_text)


        except Exception as e:
            logger.error(
                "[%s] ❌ Erro em processar_mensagem: %s | Traceback: %s",
                self.redis_key,
                str(e),
                repr(e)
            )
            await asyncio.sleep(1)


    def _is_valid_agent_source(self, source: str) -> bool:
        """
        ✅ Valida se a origem é um agente conhecido
        
        Agentes válidos:
        - "user": Mensagem do usuário (via UserProxy)
        - "talker": Assistente que fala com usuário
        - "coordinator": Orquestrador de fluxo
        - "finalizer": Responsável por encerrar
        """
        valid_sources = ["user", "Cliente", "talker", "coordinator", "finalizer"]
        is_valid = source in valid_sources
        
        if not is_valid:
            logger.warning(
                "[%s] ⚠️  Origem desconhecida: %s",
                self.redis_key,
                source
            )
        
        return is_valid


    async def _process_special_messages(self, source: str, content: str) -> None:
        """
        ✅ Processa mensagens especiais de agentes específicos
        
        - Finalizer com TERMINATE: extrai dados de finalização
        - Coordinator/Talker: apenas registra (nenhuma ação especial)
        """
        if source == "finalizer" and "TERMINATE" in content.upper():
            logger.info(
                "[%s] 🏁 TERMINATE recebido do finalizer",
                self.redis_key
            )
            
            if self.finalization_data is None:
                self._extract_finalization_data(content)
                logger.info(
                    "[%s] ✅ Dados de finalização extraídos",
                    self.redis_key
                )
            else:
                logger.debug(
                    "[%s] ℹ️  Dados de finalização já foram extraídos anteriormente",
                    self.redis_key
                )


    def _extract_finalization_data(self, content: str) -> None:
        """
        ✅ Extrai JSON de finalização do conteúdo do finalizer
        
        Tenta múltiplas estratégias:
        1. Procura por bloco ```json...```
        2. Procura por último objeto JSON no texto
        3. Se falhar, registra None
        """
        try:
            # ✅ Estratégia 1: JSON marcado com ```json
            match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                self.finalization_data = json.loads(match.group(1))
                logger.debug("[%s] ✅ JSON extraído de bloco ```json```", self.redis_key)
                return


            # ✅ Estratégia 2: Último objeto JSON no texto
            matches = re.findall(r"\{.*?\}", content, re.DOTALL)
            if matches:
                self.finalization_data = json.loads(matches[-1])
                logger.debug("[%s] ✅ JSON extraído de objeto no texto", self.redis_key)
                return


            # ✅ Se não conseguir parsear, loga aviso
            logger.warning("[%s] ⚠️  Nenhum JSON válido encontrado em finalization_data", self.redis_key)
            self.finalization_data = None


        except json.JSONDecodeError as e:
            logger.error(
                "[%s] ❌ Erro ao fazer parse do JSON de finalização: %s",
                self.redis_key,
                str(e)
            )
            self.finalization_data = None
        
        except Exception as e:
            logger.error(
                "[%s] ❌ Erro inesperado em _extract_finalization_data: %s",
                self.redis_key,
                str(e)
            )
            self.finalization_data = None


    def is_conversation_finished(self) -> bool:
        """
        ✅ Verifica se conversa foi finalizada
        
        Retorna True apenas se:
        - Finalizer enviou TERMINATE E
        - Dados de finalização foram extraídos com sucesso
        """
        is_finished = self.finalization_data is not None
        
        if is_finished:
            logger.info(
                "[%s] ✅ Conversa marcada como finalizada",
                self.redis_key
            )
        
        return is_finished


    def finalize_conversation(self) -> Dict[str, Any]:
        """
        ✅ Finaliza conversa e retorna relatório completo
        
        Retorna:
        {
            "session_id": str,
            "status": "finalizado|incompleto",
            "duration_seconds": float,
            "total_messages": int,
            "conversation_history": list,
            "finalization_data": dict,
            "sucesso": bool,
            "timestamp_final": str
        }
        """
        duration = (datetime.now() - self.start_time).total_seconds()
        
        status = "finalizado" if self.finalization_data else "incompleto"
        
        report = {
            "session_id": self.session_id,
            "status": status,
            "duration_seconds": round(duration, 2),
            "total_messages": len(self.conversation_history),
            "conversation_history": self.conversation_history,
            "finalization_data": self.finalization_data,
            "sucesso": bool(self.finalization_data),
            "timestamp_final": datetime.now().isoformat(),
        }
        
        logger.info(
            "[%s] 📊 RELATÓRIO FINAL | Status: %s | Duração: %.2fs | Mensagens: %d",
            self.redis_key,
            status,
            duration,
            len(self.conversation_history)
        )
        
        return report


    async def cleanup(self) -> None:
        """
        ✅ Limpa recursos da conversa
        
        Chamado no final da sessão para:
        - Fechar conexões
        - Salvar histórico (opcional)
        - Liberar memória
        """
        logger.info(
            "[%s] 🧹 Limpando ConversationManager",
            self.redis_key
        )
        
        try:
            # ✅ Limpa história (opcional)
            self.conversation_history = []
            
            # ✅ Marca como limpo
            logger.info(
                "[%s] ✅ Cleanup finalizado",
                self.redis_key
            )
        
        except Exception as e:
            logger.error(
                "[%s] ❌ Erro durante cleanup: %s",
                self.redis_key,
                str(e)
            )

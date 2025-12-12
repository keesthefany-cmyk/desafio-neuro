from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_agentchat.conditions import TextMentionTermination

from app.agents.agent_builder import AgentBuilder
from app.services.conversation_manager import ConversationManager
from app.agents.user_proxy_agent import UserProxyAgent
from app.services.message_processor import MessageProcessor
from app.configs.logging_config import configurar_logger
from app.services.queue_manager import QueueManager
from app.configs.config import OpenAIConstants, PathSystemPrompts

import yaml

logger = configurar_logger(__name__)

class AiOrchestrator:
    def __init__(
        self,
        session_id: str,
        chat_key: str,
        user_type: str,
        openai_api_key: str,
        queue_manager: QueueManager,
        phone: str = "",
    ):
        self.session_id = session_id
        self.chat_key = chat_key
        self.user_type = user_type
        self.openai_api_key = openai_api_key
        self.queue_manager = queue_manager
        self.conversation_manager: Optional[ConversationManager] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.model_clients: Dict[str, OpenAIChatCompletionClient] = {}
        self.graph_flow: Optional[GraphFlow] = None
        self.agents: Dict[str, Optional[BaseChatAgent]] = {}
        self.final_talker_message: Optional[str] = None
        self.is_finished: bool = False
        self.phone = phone
        logger.info("[%s] ✨ AiOrchestrator inicializado", self.chat_key)

    async def prepare(self) -> None:
        """Prepara o orquestrador: clientes OpenAI, agentes e grafo"""
        logger.info("[%s] 🔧 Iniciando prepare()", self.chat_key)
        
        self._initialize_openai_clients()
        self.message_processor = MessageProcessor(self.chat_key)
        self.conversation_manager = ConversationManager(
            session_id=self.session_id,
            redis_key=self.chat_key,
            message_processor=self.message_processor,
        )
        
        await self._initialize_agents_and_graph()
        logger.info("[%s] ✅ prepare() concluído", self.chat_key)

    def _initialize_openai_clients(self):
        """Inicializa clientes OpenAI para diferentes modelos"""
        logger.debug("[%s] 📡 Inicializando clientes OpenAI", self.chat_key)
        
        self.model_clients = {
            "model1": OpenAIChatCompletionClient(
                model=OpenAIConstants.MODEL1,
                api_key=self.openai_api_key,
                temperature=OpenAIConstants.TEMPERATURE,
                max_completion_tokens=OpenAIConstants.MAX_COMPLETION_TOKENS_2500,
            )
        }

    async def _initialize_agents_and_graph(self):
        """Cria agentes especializados e constrói o grafo de conversa"""
        logger.info("[%s] 🤖 Inicializando agentes", self.chat_key)
        
        prompts = await self._load_prompts()
        agent_builder = AgentBuilder()
        
        base_agents = await agent_builder.create_base_agents(prompts, self.model_clients)
        specialized_agents = await agent_builder.create_specialized_agents(prompts, self.model_clients)
        user_proxy = UserProxyAgent(
            name="user",
            chat_key=self.chat_key,
            phone=self.phone,
            termination_string="TERMINATE",
            description="User Proxy",
            queue_manager=self.queue_manager,
            user_type=self.user_type,
        )
        
        self.agents = agent_builder.get_agent_configuration(
            agent_type="onboarding",
            base_agents=base_agents,
            specialized_agents=specialized_agents,
        )
        
        await self._build_graph_flow(self.agents, user_proxy)
        logger.info("[%s] ✅ Agentes inicializados", self.chat_key)

    async def _build_graph_flow(self, agents, userproxy):
        """Constrói o grafo de fluxo: UserProxy → Coordinator → Talker → Finalizer"""
        logger.info("[%s] 🔗 Construindo grafo de fluxo", self.chat_key)
        
        builder = DiGraphBuilder()
        
        coordinator = agents.get("coordinator")
        talker = agents.get("talker")
        finalizer = agents.get("finalizer")
        
        valid_agents = [userproxy, coordinator, talker, finalizer]
        valid_agents = [a for a in valid_agents if a]
        
        for agent in valid_agents:
            builder.add_node(agent)
            logger.debug("[%s] 📍 Agente adicionado: %s", self.chat_key, agent.name if hasattr(agent, 'name') else str(agent))
        
        # Fluxo: UserProxy → Coordinator → Talker → Finalizer
        builder.set_entry_point(userproxy)
        builder.add_edge(userproxy, coordinator)
        builder.add_edge(coordinator, talker)
        
        # if finalizer:
            # builder.add_edge(talker, finalizer)
        
        graph = builder.build()
        
        self.graph_flow = GraphFlow(
            graph=graph,
            termination_condition=TextMentionTermination(text="TERMINATE"),
            participants=valid_agents,
        )
        
        logger.info("[%s] ✅ Grafo construído com %d agentes", self.chat_key, len(valid_agents))

    async def execute(self, first_message: str, employee_name: str = ""):
        """
        Executa o fluxo de conversa com a mensagem inicial
        
        Args:
            first_message: Mensagem inicial do usuário
            employee_name: Nome do funcionário (opcional)
        
        Returns:
            Última mensagem do talker
        """
        logger.info("[%s] 🚀 Executando fluxo com mensagem: %s", self.chat_key, first_message[:50])
        
        task = TextMessage(
            content=(
                f"Data e hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"Tipo de usuário: {self.user_type}\n"
                f"Funcionário: {employee_name}\n\n"
                f"Mensagem:\n{first_message}"
            ),
            source="user",
        )
        
        await self._run_graph_flow(task)
        
        logger.info(
            "[%s] ✅ Fluxo concluído | Final message: %s",
            self.chat_key,
            (self.final_talker_message[:50] if self.final_talker_message else "None")
        )
        
        return self.final_talker_message or ""

    async def _run_graph_flow(self, initial_message: TextMessage):
        """
        ✅ CORRIGIDO: Executa o fluxo do grafo de forma sequencial
        
        Mantém a sessão aberta até receber TERMINATE do finalizer.
        Não interrompe prematoriamente.
        """
        logger.info("[%s] 🔄 Iniciando _run_graph_flow", self.chat_key)
        
        event_count = 0
        
        async for event in self.graph_flow.run_stream(task=initial_message):
            event_count += 1
            
            await self._handle_graph_event(event)
            
            # ✅ CORRIGIDO: Apenas quebra se talker gerou TERMINATE explicitamente
            if self.final_talker_message and "TERMINATE" in self.final_talker_message:
                logger.info(
                    "[%s] 🏁 TERMINATE detectado! Encerrando após %d eventos",
                    self.chat_key,
                    event_count
                )
                self.is_finished = True
                break
            
            # ✅ NÃO quebra apenas por is_conversation_finished()
            # Deixa o GraphFlow natural chegar ao fim
        
        logger.info(
            "[%s] ✅ _run_graph_flow concluído após %d eventos",
            self.chat_key,
            event_count
        )

    async def _handle_graph_event(self, event):
        """
        ✅ CORRIGIDO: Processa evento do grafo com logging detalhado
        
        - Captura mensagens de múltiplas formas
        - Log completo da conversa interna
        - Evita duplicação
        """
        messages = []
        
        # ✅ Tenta extrair mensagem de múltiplas formas
        if hasattr(event, "chat_message") and event.chat_message:
            messages = [event.chat_message]
            logger.debug("[%s] 📩 Event type: ChatMessage", self.chat_key)
            
        elif hasattr(event, "messages") and event.messages:
            messages = event.messages
            logger.debug("[%s] 📩 Event type: Messages (%d)", self.chat_key, len(messages))
            
        elif hasattr(event, "message") and event.message:
            messages = [event.message]
            logger.debug("[%s] 📩 Event type: SingleMessage", self.chat_key)
        
        else:
            # ✅ Registra eventos que não tinham mensagem extraível
            logger.warning(
                "[%s] ⚠️  Event sem mensagem: %s | Atributos: %s",
                self.chat_key,
                type(event).__name__,
                [attr for attr in dir(event) if not attr.startswith('_')][:5]
            )
            return
        
        for idx, msg in enumerate(messages, 1):
            content = msg.content if hasattr(msg, 'content') else str(msg)
            
            if isinstance(content, (list, dict)):
                content_str = str(content)
            else:
                content_str = str(content) if content else ""
            
            # ✅ Agora é sempre string
            content_preview = content_str[:80].replace('\n', ' ')
            
            logger.info(
                "[%s] 💬 [Mensagem %d/%d] %s: %s",
                self.chat_key,
                idx,
                len(messages),
                msg.source.upper() if hasattr(msg, 'source') else "UNKNOWN",
                content_preview
            )
            
            await self.conversation_manager.processar_mensagem(msg)
            
            if hasattr(msg, 'source') and msg.source == "talker":
                self.final_talker_message = content_str
                logger.debug(
                    "[%s] 📤 Talker message capturado para retorno",
                    self.chat_key
                )

    async def _load_prompts(self) -> Dict[str, Any]:
        """Carrega prompts do arquivo YAML"""
        logger.debug("[%s] 📄 Carregando prompts de %s", self.chat_key, PathSystemPrompts.PROMPTS_PATH)
        
        with open(Path(PathSystemPrompts.PROMPTS_PATH), "r", encoding="utf-8") as f:
            prompts = yaml.safe_load(f)
        
        logger.debug("[%s] ✅ Prompts carregados: %s", self.chat_key, list(prompts.keys()))
        
        return prompts

    async def cleanup(self):
        """Limpa recursos da sessão"""
        logger.info("[%s] 🧹 Iniciando cleanup", self.chat_key)
        
        self.is_finished = True
        
        if self.conversation_manager:
            await self.conversation_manager.cleanup()
        
        logger.info("[%s] ✅ Cleanup finalizado", self.chat_key)

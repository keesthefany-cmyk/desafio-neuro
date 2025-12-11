from typing import Optional, Dict, Any, AsyncGenerator, List
from datetime import datetime
from pathlib import Path
import yaml
import asyncio

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.memory import ListMemory, MemoryContent, MemoryMimeType

from app.agents.agent_builder import AgentBuilder
from app.services.conversation_manager import ConversationManager
from app.agents.user_proxy_agent import UserProxyAgent
from app.services.message_processor import MessageProcessor
from app.configs.logging_config import configurar_logger
from app.services.queue_manager import QueueManager
from app.configs.config import OpenAIConstants, PathSystemPrompts

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
        self.phone = phone

        self.conversation_manager: Optional[ConversationManager] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.model_clients: Dict[str, OpenAIChatCompletionClient] = {}
        self.graph_flow: Optional[GraphFlow] = None
        self.agents: Dict[str, Optional[BaseChatAgent]] = {}

        self.final_talker_message: Optional[str] = None
        self.talker_messages: list[str] = []
        self.is_finished: bool = False
        
        # Memória compartilhada
        self.coordinator_history: List[str] = []
        self.collected_data: Dict[str, str] = {}
        self.current_field_index: int = 0
        
        # UserProxy reutilizável
        self.user_proxy: Optional[UserProxyAgent] = None
        
        self._coordinator_done_event = asyncio.Event()

        logger.info("[%s] AiOrchestrator inicializado", self.chat_key)

    async def prepare(self) -> None:
        self._initialize_openai_clients()
        self.message_processor = MessageProcessor(self.chat_key)

        self.conversation_manager = ConversationManager(
            session_id=self.session_id,
            redis_key=self.chat_key,
            message_processor=self.message_processor,
        )

        await self._initialize_agents_and_graph()

    def _initialize_openai_clients(self):
        self.model_clients = {
            "model1": OpenAIChatCompletionClient(
                model=OpenAIConstants.MODEL1,
                api_key=self.openai_api_key,
                temperature=OpenAIConstants.TEMPERATURE,
                max_completion_tokens=OpenAIConstants.MAX_COMPLETION_TOKENS_2500,
            )
        }

    async def _initialize_agents_and_graph(self):
        prompts = await self._load_prompts()
        agent_builder = AgentBuilder()
        
        # Criar memória do coordinator UMA VEZ
        coordinator_memory = await self._create_coordinator_memory()

        base_agents = await agent_builder.create_base_agents(
            prompts, self.model_clients, coordinator_memory=coordinator_memory
        )
        specialized_agents = await agent_builder.create_specialized_agents(prompts, self.model_clients)

        # Criar UserProxy UMA VEZ
        self.user_proxy = UserProxyAgent(
            name="user",
            chat_key=self.chat_key,
            phone="",
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

        # Construir GraphFlow UMA VEZ
        await self._build_graph_flow(self.agents, self.user_proxy)

    async def _create_coordinator_memory(self) -> ListMemory:
        """Cria memória do coordinator com regras e histórico."""
        from app.configs.config import MemoryConstants
        
        coordinator_memory = ListMemory(name="coordinator_memory")
        
        # Carregar regras
        with open(MemoryConstants.ONBOARDING_RULES_FILE, "r", encoding="utf-8") as f:
            rules_content = f.read()
        
        rules_memory = MemoryContent(
            content=rules_content,
            mime_type=MemoryMimeType.MARKDOWN
        )
        await coordinator_memory.add(rules_memory)
        
        return coordinator_memory

    async def _build_graph_flow(self, agents, user_proxy):
        builder = DiGraphBuilder()

        coordinator = agents.get("coordinator")
        talker = agents.get("talker")
        finalizer = agents.get("finalizer")

        valid_agents = [user_proxy, coordinator, talker]
        if finalizer:
            valid_agents.append(finalizer)
        valid_agents = [a for a in valid_agents if a]

        for agent in valid_agents:
            builder.add_node(agent)

        builder.set_entry_point(user_proxy)

        builder.add_edge(user_proxy, coordinator)
        builder.add_edge(coordinator, talker)
        # Finalizer não recebe edge automática

        graph = builder.build()

        self.graph_flow = GraphFlow(
            graph=graph,
            termination_condition=TextMentionTermination(text="TERMINATE"),
            participants=valid_agents,
        )

    async def execute(
        self, first_message: str, employee_name: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        Async generator que retorna cada mensagem do Talker assim que produzida.
        Reutiliza os agentes e GraphFlow já criados em prepare().
        """
        task = TextMessage(
            content=(
                f"Data e hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"Tipo de usuário: {self.user_type}\n"
                f"Funcionário: {employee_name}\n\n"
                f"Mensagem:\n{first_message}"
            ),
            source="user",
        )

        async for talker_msg in self._run_graph_flow_stream(task):
            yield talker_msg

    async def _run_graph_flow_stream(self, initial_message: TextMessage) -> AsyncGenerator[str, None]:
        """
        Executa o fluxo do grafo e envia mensagens do Talker em tempo real,
        evitando duplicatas do Coordinator e do Talker.
        """
        processed_talker_messages = set()
        processed_coordinator_messages = set()
        user_message_processed = False

        async for event in self.graph_flow.run_stream(task=initial_message):
            messages = []

            if hasattr(event, "chat_message") and event.chat_message:
                messages = [event.chat_message]
            elif hasattr(event, "messages"):
                messages = event.messages
            elif hasattr(event, "message"):
                messages = [event.message]

            for msg in messages:
                # Mensagem do usuário
                if msg.source == "user":
                    if user_message_processed:
                        logger.debug("[%s] Mensagem do user já processada, ignorando duplicata", self.chat_key)
                        continue
                    user_message_processed = True
                    logger.debug("[%s] %s: %s", self.chat_key, msg.source, msg.content)

                # Mensagem do Coordinator
                elif msg.source == "coordinator":
                    content_str = str(msg.content)
                    msg_hash = hash(content_str)
                    if msg_hash in processed_coordinator_messages:
                        logger.debug("[%s] Coordinator já gerou esta mensagem nesta execução, ignorando", self.chat_key)
                        continue
                    processed_coordinator_messages.add(msg_hash)
                    self.coordinator_history.append(content_str)
                    logger.debug("[%s] %s: %s", self.chat_key, msg.source, content_str)
                    self._coordinator_done_event.set()  # libera Talker

                # Mensagem do Talker
                elif msg.source == "talker":
                    await self._coordinator_done_event.wait()
                    content_str = str(msg.content)
                    msg_hash = hash(content_str)
                    if msg_hash in processed_talker_messages:
                        logger.debug("[%s] Mensagem do Talker já processada, ignorando duplicata", self.chat_key)
                        continue
                    processed_talker_messages.add(msg_hash)
                    self.final_talker_message = content_str
                    self.talker_messages.append(content_str)
                    logger.debug("[%s] %s: %s", self.chat_key, msg.source, content_str)

                    yield content_str

            if self.conversation_manager.is_conversation_finished():
                self.is_finished = True
                break

    async def _load_prompts(self) -> Dict[str, Any]:
        with open(Path(PathSystemPrompts.PROMPTS_PATH), "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def cleanup(self):
        logger.info("[%s] Cleanup finalizado", self.chat_key)
        self.is_finished = True

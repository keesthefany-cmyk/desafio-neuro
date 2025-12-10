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

        base_agents = await agent_builder.create_base_agents(prompts, self.model_clients)
        specialized_agents = await agent_builder.create_specialized_agents(prompts, self.model_clients)

        user_proxy = UserProxyAgent(
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

        await self._build_graph_flow(self.agents, user_proxy)

    async def _build_graph_flow(self, agents, userproxy):
        builder = DiGraphBuilder()

        coordinator = agents.get("coordinator")
        talker = agents.get("talker")
        finalizer = agents.get("finalizer")

        valid_agents = [userproxy, coordinator, talker, finalizer]
        valid_agents = [a for a in valid_agents if a]

        for agent in valid_agents:
            builder.add_node(agent)

        builder.set_entry_point(userproxy)

        # Fluxo: UserProxy → Coordinator → Talker → Finalizer (quando decidir terminar)
        builder.add_edge(userproxy, coordinator)
        builder.add_edge(coordinator, talker)
        if finalizer:
            builder.add_edge(talker, finalizer)

        graph = builder.build()

        self.graph_flow = GraphFlow(
            graph=graph,
            termination_condition=TextMentionTermination(text="TERMINATE"),
            participants=valid_agents,
        )

    async def execute(self, first_message: str, employee_name: str = ""):
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
        return self.final_talker_message or ""

    async def _run_graph_flow(self, initial_message: TextMessage):
        """
        Executa o fluxo do grafo de forma linear e sequencial:
        UserProxy → Coordinator → Talker → UserProxy → (repeat até TERMINATE)
        """
        async for event in self.graph_flow.run_stream(task=initial_message):
            await self._handle_graph_event(event)

            if self.conversation_manager.is_conversation_finished():
                self.is_finished = True
                break


    async def _handle_graph_event(self, event):
        messages = []

        if hasattr(event, "chat_message") and event.chat_message:
            messages = [event.chat_message]
        elif hasattr(event, "messages"):
            messages = event.messages
        elif hasattr(event, "message"):
            messages = [event.message]

        for msg in messages:
            logger.debug("[%s] %s: %s", self.chat_key, msg.source, msg.content)
            await self.conversation_manager.processar_mensagem(msg)

            if msg.source == "talker":
                self.final_talker_message = msg.content


    async def _load_prompts(self) -> Dict[str, Any]:
        with open(Path(PathSystemPrompts.PROMPTS_PATH), "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def cleanup(self):
        logger.info("[%s] Cleanup finalizado", self.chat_key)
        self.is_finished = True
from typing import Dict, Any
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.memory import ListMemory, MemoryContent, MemoryMimeType
from autogen_core.tools import FunctionTool
from app.configs.config import MemoryConstants
from app.agents.agent_factory import (
    create_talker_agent,
    create_coordinator_agent,
    create_finalizer_agent,
)
from app.configs.logging_config import configurar_logger

logger = configurar_logger(__name__)

BUFFER_SIZE = MemoryConstants.BUFFER_SIZE
ONBOARDING_RULES_FILE = MemoryConstants.ONBOARDING_RULES_FILE


async def search_knowledge_base(query: str) -> str: 
    return f"Resultado simulado da base de conhecimento para: {query}"

async def store_employee_data(employee_id: str, data: dict) -> str: 
    return f"Dados do funcionário {employee_id} armazenados com sucesso" 
async def update_knowledge_base(entry_id: str, content: str) -> str: 
    return f"Entrada {entry_id} atualizada na base de conhecimento" 
async def check_onboarding_status(employee_id: str) -> str: 
    return f"Status de onboarding do funcionário {employee_id}: Pendente" 

search_knowledge_base_tool = FunctionTool(search_knowledge_base, description="Buscar informações na base de conhecimento") 

store_employee_data_tool = FunctionTool(store_employee_data, description="Armazenar dados de funcionário") 
update_knowledge_base_tool = FunctionTool(update_knowledge_base, description="Atualizar base de conhecimento") 
check_onboarding_status_tool = FunctionTool(check_onboarding_status, description="Verificar status de onboarding")

class AgentBuilder:
    def __init__(self):
        from autogen_core.model_context import BufferedChatCompletionContext
        self.model_context = BufferedChatCompletionContext(buffer_size=BUFFER_SIZE)

    async def create_base_agents(
        self,
        prompts: Dict[str, Any],
        model_clients: Dict[str, OpenAIChatCompletionClient],
    ) -> Dict[str, AssistantAgent]:

        with open(ONBOARDING_RULES_FILE, "r", encoding="utf-8") as f:
            rules_content = f.read()

        rules_memory = MemoryContent(
            content=rules_content,
            mime_type=MemoryMimeType.MARKDOWN
        )

        coordinator_memory = ListMemory(name="coordinator_memory")
        await coordinator_memory.add(rules_memory)

        coordinator = create_coordinator_agent(
            name="coordinator",
            system_message=prompts["coordinator-prompt"]["prompt"],
            description="Gestor especializado em processos de onboarding",
            model_client=model_clients["model1"],
            tools=[
                search_knowledge_base_tool,
                store_employee_data_tool,
                update_knowledge_base_tool,
    
                check_onboarding_status_tool,
            ],
            reflect_on_tool_use=True,
            max_tool_iterations=1,
            model_context=self.model_context,
            memory=[coordinator_memory],
        )

        finalizer = create_finalizer_agent(
            name="finalizer",
            system_message=prompts["finalizer-prompt"]["prompt"],
            description="Agente responsável por finalizar processos de onboarding",
            model_client=model_clients["model1"],
            model_context=self.model_context,
        )

        return {
            "coordinator": coordinator,
            "finalizer": finalizer,
        }

    async def create_specialized_agents(
        self,
        prompts: Dict[str, Any],
        model_clients: Dict[str, OpenAIChatCompletionClient],
    ) -> Dict[str, AssistantAgent]:

        with open(ONBOARDING_RULES_FILE, "r", encoding="utf-8") as f:
            rules_content = f.read()

        rules_memory = MemoryContent(
            content=rules_content,
            mime_type=MemoryMimeType.MARKDOWN
        )

        talker_memory = ListMemory(name="talker_memory")
        await talker_memory.add(rules_memory)

        talker = create_talker_agent(
            name="talker",
            description="Assistente de onboarding especializado em WhatsApp",
            system_message=prompts["talker-prompt"]["prompt"],
            model_client=model_clients["model1"],
            model_context=self.model_context,
            memory=[talker_memory],
        )

        return {
            "talker": talker,
        }

    def get_agent_configuration(
        self,
        agent_type: str,
        base_agents: Dict[str, AssistantAgent],
        specialized_agents: Dict[str, AssistantAgent],
    ) -> Dict[str, AssistantAgent]:

        configs = {
            "onboarding": {
                "coordinator": base_agents["coordinator"],
                "talker": specialized_agents["talker"],
                "finalizer": base_agents["finalizer"],
            }
        }

        if agent_type not in configs:
            raise ValueError(f"Tipo de agente '{agent_type}' não reconhecido")

        return configs[agent_type]

    async def cleanup(self):
        pass

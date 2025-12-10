from autogen_agentchat.agents import AssistantAgent
from app.configs.logging_config import configurar_logger

logger = configurar_logger(__name__)


def _create_base_agent(
    name: str,
    system_message: str,
    description: str,
    model_client,
    tools=None,
    reflect_on_tool_use: bool = True,
    max_tool_iterations: int = 1,
    model_context=None,
    memory=None,
):
    """
    Cria um agente AssistantAgent com validações e defaults seguros.
    Usado internamente pelas funções: talker, coordinator e finalizer.
    """

    if model_client is None:
        raise ValueError(f"[Agent:{name}] model_client não pode ser None")

    logger.info(f"[Agent:{name}] Inicializando agente ({description})")

    return AssistantAgent(
        name=name,
        system_message=system_message,
        description=description,
        model_client=model_client,
        tools=tools or [],
        reflect_on_tool_use=reflect_on_tool_use,
        max_tool_iterations=max_tool_iterations,
        model_context=model_context,
        memory=memory
    )


def create_talker_agent(
    name,
    system_message,
    description,
    model_client,
    model_context=None,
    memory=None
):
    """Cria o agente de conversa primário (talker)."""
    return _create_base_agent(
        name=name,
        system_message=system_message,
        description=description,
        model_client=model_client,
        tools=[],            # talker normalmente não usa ferramentas
        reflect_on_tool_use=False,
        max_tool_iterations=1,  # ✅ MUDADO DE 0 PARA 1
        model_context=model_context,
        memory=memory
    )


def create_coordinator_agent(
    name,
    system_message,
    description,
    model_client,
    tools=None,
    reflect_on_tool_use=True,
    max_tool_iterations=1,
    model_context=None,
    memory=None
):
    """Cria o coordenador do GraphFlow, responsável por chamar tools."""
    return _create_base_agent(
        name=name,
        system_message=system_message,
        description=description,
        model_client=model_client,
        tools=tools,
        reflect_on_tool_use=reflect_on_tool_use,
        max_tool_iterations=max_tool_iterations,
        model_context=model_context,
        memory=memory
    )


def create_finalizer_agent(
    name,
    system_message,
    description,
    model_client,
    tools=None,
    reflect_on_tool_use=False,
    max_tool_iterations=1,  # ✅ MUDADO DE 0 PARA 1
    model_context=None,
    memory=None
):
    """
    Cria o agente finalizador, responsável por enviar TERMINATE + JSON final.
    """
    return _create_base_agent(
        name=name,
        system_message=system_message,
        description=description,
        model_client=model_client,
        tools=tools,   # geralmente vazio, mas permitido
        reflect_on_tool_use=reflect_on_tool_use,
        max_tool_iterations=max_tool_iterations,
        model_context=model_context,
        memory=memory
    )
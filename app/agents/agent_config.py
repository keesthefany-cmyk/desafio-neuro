from typing import Optional, Any, Dict

class AgentConfig:
    """
    Configuração padronizada para criação de agentes.
    Parâmetros obrigatórios: name, system_message, model_client
    """
    def __init__(
        self,
        name: Optional[str] = None,
        system_message: Optional[str] = None,
        description: Optional[str] = None,
        model_client: Optional[Any] = None,
        model_context: Optional[Any] = None,
        workbench: Optional[Any] = None,
        memory: Optional[Any] = None,
        tools: Optional[Any] = None,
        # business_rules_file: Optional[str] = None,
        reflect_on_tool_use: Optional[bool] = None,
        max_tool_iterations: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
        unidade: Optional[str] = None
    ):
        # Validação explícita de obrigatórios
        if not name:
            raise ValueError("AgentConfig: parâmetro obrigatório 'name' ausente.")
        if not system_message:
            raise ValueError("AgentConfig: parâmetro obrigatório 'system_message' ausente.")
        if not model_client:
            raise ValueError("AgentConfig: parâmetro obrigatório 'model_client' ausente.")
        self.unidade = unidade
        self.name = name
        self.system_message = system_message
        self.description = description
        self.model_client = model_client
        self.model_context = model_context
        self.workbench = workbench
        self.memory = memory
        self.tools = tools
        # self.business_rules_file = business_rules_file
        self.reflect_on_tool_use = reflect_on_tool_use
        self.max_tool_iterations = max_tool_iterations
        self.extra = extra or {}

    def get(self, key, default=None):
        return getattr(self, key, self.extra.get(key, default))

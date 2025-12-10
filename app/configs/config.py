import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class RedisConstants:
    REDIS_URL: str = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', 6379)}"
    KEY_CONVERSATION: str = "conversation"
    KEY_STATUS: str = "status"
    KEY_INCOME_MESSAGES: str = "income_messages"
    KEY_OUTCOME_MESSAGES: str = "outcome_messages"

@dataclass
class LLMProviderConstants:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")

class OpenAIConstants:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    MODEL1 : str = os.getenv("MODEL1", "gpt-4o-mini")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.2"))
    MAX_COMPLETION_TOKENS_2500: int = int(os.getenv("MAX_COMPLETION_TOKENS_2500", "2500"))
    MAX_COMPLETION_TOKENS_4000: int = int(os.getenv("MAX_COMPLETION_TOKENS_4000", "4000"))
    MAX_COMPLETION_TOKENS_250: int = int(os.getenv("MAX_COMPLETION_TOKENS_250", "250"))
    MAX_COMPLETION_TOKENS_300: int = int(os.getenv("MAX_COMPLETION_TOKENS_300", "300"))
    
@dataclass
class MemoryConstants:
    TOKEN_LIMIT: int = int(os.getenv("TOKEN_LIMIT", "80000"))
    BUFFER_SIZE: int = int(os.getenv("BUFFER_SIZE", "1000"))
    PROMPTS_PATH: Path = Path(os.getenv("PROMPTS_PATH", "app/templates/prompts.yaml"))
    ONBOARDING_RULES_FILE: Path = Path(os.getenv("RULES_PATH", "app/templates/rules.yaml"))
    ONBOARDING_RULES_FILE: Path = Path(os.getenv("BUSINESS_RULES_FILE", "app/templates/rules.md"))
@dataclass
class PathSystemPrompts:
    PROMPTS_PATH: Path = Path(os.getenv("PROMPTS_PATH", "app/templates/prompts.yaml"))
    RULES_PATH: Path = Path(os.getenv("RULES_PATH", "app/templates/rules.yaml"))
    ONBOARDING_RULES_FILE: Path = Path(os.getenv("BUSINESS_RULES_FILE", "app/templates/rules.md"))


@dataclass
class ConversationContants:
    CONVERSATION_TIMEOUT: int = int(os.getenv("CONVERSATION_TIMEOUT", 60))
    ACCUMULATE_DELAY: int = int(os.getenv("ACCUMULATE_DELAY", 2))
    MAX_TURNS: int = int(os.getenv("MAX_TURNS", 15))


@dataclass
class ServerConstants:
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", 7000))
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    WORKERS: int = int(os.getenv("WORKERS", 1))


@dataclass
class ElasticsearchConstants:
    ES_HOST: str = os.getenv("ES_HOST")
    ES_USER: str = os.getenv("ES_USER")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD")
    NEURO_BASE_INDEX: str = os.getenv("neuro_index_name")
    POLITICAS_BASE_INDEX: str = os.getenv("politicas_index_name")


# ===========================
# CONFIG FINAL
# ===========================
@dataclass
class AppConfig:
    redis: RedisConstants = field(default_factory=RedisConstants)
    llm: LLMProviderConstants = field(default_factory=LLMProviderConstants)
    paths: PathSystemPrompts = field(default_factory=PathSystemPrompts)
    memory: MemoryConstants = field(default_factory=MemoryConstants)
    conversation: ConversationContants = field(default_factory=ConversationContants)
    server: ServerConstants = field(default_factory=ServerConstants)
    elastic: ElasticsearchConstants = field(default_factory=ElasticsearchConstants)


config = AppConfig()

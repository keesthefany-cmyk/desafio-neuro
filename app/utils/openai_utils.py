from openai import OpenAI
from app.configs.config import config


def test_openai_connection():
    """
    Testa se a API OpenAI está acessível e a chave funciona.
    """
    try:
        client = OpenAI(api_key=config.llm.OPENAI_API_KEY)
        models = client.models.list()
        return {"status": "ok", "models_count": len(models.data)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
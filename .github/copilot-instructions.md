# Copilot / AI Agent Instructions for this Repository

This file contains concise, actionable guidance for AI coding agents working on this codebase. It focuses on the project's architecture, key integration points, developer workflows, and concrete examples you can use to make safe, consistent changes.

1) Big picture
- **API:** `main.py` starts a FastAPI app that exposes endpoints (e.g. `POST /api/onboarding/message`, health checks at `/api/health/openai`).
- **Queueing & orchestration:** Redis is used as the primary IPC. `app/services/queue_manager.py` manages per-chat queues and statuses (input buffer, `income_messages`, `outcome` queue).
- **Agent system:** `app/services/ai_orchestrator.py` builds agents (via `app/agents/agent_builder.py`) and constructs a `GraphFlow` (autogen_agentchat) composed of `coordinator`, `talker`, `finalizer`, and a `UserProxyAgent`.
- **Message processing & finalization:** `app/services/message_processor.py` normalizes messages and filters control tokens; `app/services/conversation_manager.py` keeps history and extracts finalization JSON (TERMINATE).

2) Key files to read before editing behavior
- `main.py` — entry point and lifecycle (loads prompts, starts background `tasks` loop).
- `app/services/queue_manager.py` — Redis key patterns and queue operations. Preserve key formats like `chat:{...}:income_messages`.
- `app/services/ai_orchestrator.py` — shows how agents are initialized and the GraphFlow is executed.
- `app/agents/agent_builder.py` & `app/agents/agent_factory.py` — creation and configuration of agents and tools.
- `app/templates/prompts.yaml` and `app/templates/rules.yaml` — authoritative prompts and hard rules used by agents; changes here change runtime agent behavior.
- `app/services/message_processor.py` — canonical list of control terms and JSON extraction logic. Keep control-term semantics consistent (`TERMINATE`, `#transbordo`, `#finalizar`).

3) Integration points & external dependencies
- **OpenAI / LLMs:** Clients are created in `AiOrchestrator._initialize_openai_clients` using `autogen_ext.models.openai.OpenAIChatCompletionClient`. Do not hardcode API keys — use environment variables (`OPENAI_API_KEY`).
- **Redis:** Used for ephemeral chat state and queues. Config via environment vars (`REDIS_HOST`, `REDIS_PORT`, or `REDIS_URL` for Upstash). See `app/configs/config.py`.
- **MongoDB / persistence:** The README mentions MongoDB; search `app/services` for persistence code before changing data models.
- **Tools:** Several tool functions live under `app/services/tools_service.py` (e.g., `search_knowledge_base_tool`, `ocr_gemini_identity`) and are invoked by agents — follow their signatures when editing agent calls.

4) Message & queue formats (concrete examples)
- Input buffer: `rpush` of raw user messages to `{chat_key}:<input_buffer>` (see `post_to_input_buffer`).
- Agent income message payload (what agents read): JSON pushed to `{chat_key}:income_messages`, example:
  `{"msg": "<text>", "unidade": "<user_type>", "phone": "<phone>", "rid": "<rid>"}`
- Global outcome queue: `UserProxyAgent` posts a JSON string to the global outcome queue with keys `phone`, `msg`, `chat_key` (see `app/agents/user_proxy_agent.py`). Always send strings (the system reads them as text payloads for downstream delivery).

5) Important runtime tokens and semantics (do not change lightly)
- `TERMINATE` — finalizer must emit this token followed by finalization JSON. `ConversationManager._extract_finalization_data` expects a JSON block (preferably fenced with ```json ... ``` or a JSON object in text).
- `#transbordo` — indicates handoff/transfer to human support; talker or coordinator may emit it.
- `#finalizar` — activation key used to authorize finalizer actions.
- Control terms are defined in `MessageProcessor.CONTROL_TERMS`. When modifying filtering behavior, update that file and `ConversationManager` detection logic together.

6) Developer workflows & common commands
- Local run: create `.env` as described in `README.md`, then:
  - `python main.py` (this launches uvicorn via `uvicorn.run` in `main.py`).
- Docker: `docker-compose up --build` (Dockerfile and compose are provided).
- Health checks: `GET /api/health/openai` and `GET /api/health/mcp`.
- Tests: Some scripts referenced in README (e.g., `python tests/load_test.py`). Run tests relevant to changed files only.

7) Code-style & change guidelines specific to this repo
- Preserve prompt and rules files formatting. Small prompt edits can have large behavior changes — when changing prompts, include a short test that verifies agent flow.
- Maintain Redis key formats and ChatState enumerations. Many components rely on exact status strings (e.g. `waiting_user_response`, `accumulating_first_interaction`).
- When editing message parsing or JSON extraction, ensure backward compatibility: keep both fenced ```json``` and inline `{...}` parsing strategies.
- Avoid changing termination tokens or the `finalization` JSON schema unless you update all readers (`ConversationManager`, tasks that consume finalization_data, downstream systems).

8) When you are the AI agent making changes
- Keep edits small and focused. Update unit/integration tests or add a small script to demonstrate the change where applicable.
- Reference concrete code locations in PR descriptions (e.g. "Changed JSON extraction in `app/services/message_processor.py` to handle trailing comments; updated `ConversationManager._extract_finalization_data` accordingly").
- If you modify prompts in `app/templates/prompts.yaml`, include before/after examples and a short smoke test plan.

9) Where to look for examples
- Prompt-driven agent rules: `app/templates/prompts.yaml` (many examples and required JSON outputs).
- Agent orchestration & GraphFlow: `app/services/ai_orchestrator.py` and `app/agents/agent_builder.py`.
- Queue and protocol examples: `app/services/queue_manager.py` and `app/agents/user_proxy_agent.py`.

If anything above is unclear or you'd like more examples (e.g., full sample Redis keys, sample end-to-end JSON traces, or a small smoke test script), tell me which area to expand and I'll update this file.

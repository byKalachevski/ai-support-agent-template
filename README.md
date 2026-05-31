# AI Support Agent Template

A reusable AI support-agent service for building product support automation with a Markdown-based knowledge base, retrieval pipeline, safety policies, session memory and optional backend worker integration.

This repository is designed as a public template. Replace the example knowledge-base structure with your own product documentation, FAQ, policies and support workflows.

## What this project demonstrates

- FastAPI service structure
- AI support-agent orchestration
- Markdown knowledge-base loading
- Retrieval and scoring pipeline
- Prompt management
- Intent classification
- Safety and grounding policies
- Session memory and summarization
- Optional WebSocket worker integration
- Dockerized local deployment

## Repository structure

```text
app/
  routes/          FastAPI routes for chat, jobs, health and websocket endpoints
  schemas/         Pydantic contracts for chat, replies, retrieval and sessions
  services/        Agent orchestration, LLM client, KB loading, retrieval and policies
  utils/           Shared helpers

kb/
  README.md        Knowledge-base template overview
  01-routing/      Intent routing and classification guidance
  02-product-core/ Product description, glossary and core concepts
  ...              Additional optional support KB sections

Dockerfile
docker-compose.yml
.env.example
requirements.txt
```

## Knowledge base

The `kb/` folder is intentionally generic. It contains only README files that explain how users can structure their own documentation.

You can keep the included structure, modify it, rename folders or replace it entirely. The agent only needs readable documentation files that can be loaded and indexed.

Recommended content:

- product documentation
- FAQ
- onboarding guides
- troubleshooting guides
- billing and subscription rules
- security policies
- escalation rules
- response templates
- integration guides

Do not store secrets, API keys, access tokens, customer data or private credentials in the KB.

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
```

Health check:

```bash
curl http://127.0.0.1:8011/health
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

## Environment variables

Use `.env.example` as a safe template. Real `.env` files must not be committed.

Main variables:

- `LLM_PROVIDER` — provider label used for logs and diagnostics
- `LLM_BASE_URL` — OpenAI-compatible API base URL
- `LLM_API_KEY` — LLM provider API key
- `LLM_MODEL` — model name used by the agent
- `KB_DIR` — knowledge-base directory
- `WORKER_ENABLED` — enables optional backend worker mode
- `BACKEND_API_BASE_URL` — optional backend API URL
- `BACKEND_API_TOKEN` — optional backend worker token

## Customization workflow

1. Copy `.env.example` to `.env`.
2. Replace the `kb/` README templates with your own support documentation.
3. Adjust prompts in `app/services/llm/prompts.py`.
4. Adjust intent classification in `app/services/intents/classifier.py`.
5. Add your backend integration only if worker mode is needed.
6. Run locally with Docker or Uvicorn.

## Security notes

Before publishing or deploying:

- do not commit `.env`;
- do not commit production compose files with real paths or domains;
- do not commit API keys, tokens or private URLs;
- do not include customer data in the knowledge base;
- rotate any key that was ever committed by mistake.

## License

MIT

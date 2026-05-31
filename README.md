# AI Support Agent Template

Production-ready AI support-agent template built with FastAPI, Pydantic, Markdown knowledge bases, retrieval pipelines, session memory and optional backend worker integration.

This repository is designed as a reusable public template. Replace the knowledge-base structure, prompts and configuration with your own product documentation and support workflows.

---

## Features

- FastAPI backend architecture
- Pydantic request and response contracts
- AI support-agent orchestration
- Markdown knowledge-base support
- Retrieval and context scoring pipeline
- Prompt management
- Intent classification
- Safety and grounding policies
- Session memory and summarization
- Optional WebSocket worker integration
- Dockerized deployment

---

## Tech Stack

- Python
- FastAPI
- Pydantic
- Uvicorn
- Docker
- Docker Compose

---

## Repository Structure

~~~text
app/
  routes/          API routes
  schemas/         Pydantic models and contracts
  services/        Agent orchestration, retrieval and policies
  utils/           Shared helpers

kb/
  README.md        KB structure overview
  01-routing/      Intent routing rules
  02-product-core/ Product documentation
  03-onboarding/   Onboarding guides
  04-auth/         Authentication flows
  05-billing/      Billing and subscriptions
  06-workflows/    Automation workflows
  07-security/     Security and safety rules
  08-support/      Support and escalation rules
  09-troubleshooting/ Common issues and fixes

Dockerfile
docker-compose.yml
.env.example
requirements.txt
~~~

---

## Knowledge Base

The `kb/` directory contains a reusable template structure for organizing support documentation.

You can:

- rename folders;
- remove sections;
- add your own documentation;
- reorganize the hierarchy completely.

Recommended content:

- onboarding guides;
- FAQ;
- troubleshooting flows;
- billing rules;
- integration guides;
- response templates;
- escalation policies.

Do not store:

- API keys;
- tokens;
- passwords;
- customer data;
- private credentials.

---

## Quick Start

### Docker

~~~bash
cp .env.example .env
docker compose up --build
~~~

Health check:

~~~bash
curl http://127.0.0.1:8011/health
~~~

---

## Local Development

### Linux / macOS

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
~~~

### Windows PowerShell

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
~~~

---

## Environment Variables

Use `.env.example` as a safe template.

Main variables:

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | Provider label |
| `LLM_BASE_URL` | OpenAI-compatible API endpoint |
| `LLM_API_KEY` | Provider API key |
| `LLM_MODEL` | Model name |
| `KB_DIR` | Knowledge-base directory |
| `WORKER_ENABLED` | Enables worker mode |
| `BACKEND_API_BASE_URL` | Optional backend API |
| `BACKEND_API_TOKEN` | Optional backend token |

---

## Customization

1. Copy `.env.example` to `.env`.
2. Configure your provider credentials.
3. Replace KB templates with your own documentation.
4. Adjust prompts and intent routing if needed.
5. Run locally with Docker or Uvicorn.

---

## Security Notes

Before deployment:

- do not commit `.env`;
- do not commit API keys or tokens;
- do not include private customer data;
- review prompts and KB before production usage.

---

## License

MIT

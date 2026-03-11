# 🎀 FastAPI LangGraph Tsundere Girl Agent

A production-ready AI chatbot built with **FastAPI** and **LangGraph** that roleplays as a Tsundere character — a classic anime archetype who starts cold and dismissive but gradually warms up as the user gains affection points through kind and polite interactions.

---

## ✨ Features

- 🧠 **LangGraph Agent Workflow** — Stateful, multi-step AI agent with an `analyzer → generator` pipeline
- 💕 **Dynamic Affection System** — A score from `-10` to `+10` that dynamically shifts the character's tone from tsundere to warm
- 🛡️ **Jailbreak Guardrails** — Analyzer detects and neutralizes unsafe/jailbreak messages before they reach the generator
- 🧬 **Long-Term Memory** — Per-user persistent memory powered by `mem0ai` + `pgvector`, storing facts about the user (preferences, location, weaknesses, etc.)
- 🔄 **Streaming & Non-Streaming** — Both SSE streaming and standard JSON response modes
- 🔐 **JWT Authentication** — Session-based login system with token expiry
- 🚦 **Rate Limiting** — Per-endpoint rate limits via `slowapi`
- 📊 **Observability** — LLM tracing via Langfuse, Prometheus metrics, and structured JSON logging via `structlog`
- 🐘 **PostgreSQL + pgvector** — Conversation checkpointing (LangGraph) and vector memory storage
- 🖥️ **Built-in Frontend** — Vanilla HTML/JS/CSS demo UI served at `/app`
- 🐳 **Docker-ready** — Full Docker Compose stack

---

## 🏗️ Architecture

```
User Request
    │
    ▼
FastAPI (REST API + SSE Streaming)
    │
    ▼
LangGraph StateGraph
    ├── [analyzer node]    ← Sentiment analysis, jailbreak detection, name extraction
    └── [generator node]  ← Tsundere persona response, tone adapts to affection score
    │
    ▼
OpenAI LLM (via LangChain)
    │
    ├── Langfuse (tracing)
    ├── PostgreSQL (checkpointing + pgvector memory)
    └── mem0ai (long-term user memory)
```

### Graph State (`GraphState`)

| Field | Type | Description |
|---|---|---|
| `messages` | `list[AnyMessage]` | Full conversation history (uses `add_messages` reducer) |
| `affection_score` | `int` | Range: `-10` to `+10`; controls character tone |
| `long_term_memory` | `str` | Retrieved user facts injected into the system prompt |
| `user_name` | `str \| None` | Extracted user name |
| `is_safe` | `bool` | Whether the latest message passed safety checks |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL with `pgvector` extension (or use Docker)
- OpenAI API key
- Langfuse account (optional but recommended for tracing)
- [`uv`](https://github.com/astral-sh/uv) package manager

### 1. Clone and Install

```bash
git clone https://github.com/your-username/fastapi-langgraph-tsundere-girl-agent.git
cd fastapi-langgraph-tsundere-girl-agent

# Install uv and dependencies
make install
```

### 2. Configure Environment

```bash
cp .env.example .env.development
```

Edit `.env.development` with your credentials:

```env
# LLM
OPENAI_API_KEY="sk-..."
DEFAULT_LLM_MODEL=gpt-4o-mini

# Database
POSTGRES_HOST=localhost
POSTGRES_DB=mydb
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_PORT=5432

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY="pk-..."
LANGFUSE_SECRET_KEY="sk-..."
LANGFUSE_HOST=https://cloud.langfuse.com

# JWT
JWT_SECRET_KEY="your-secret-key"
```

### 3. Run the Application

**Development (with hot-reload):**
```bash
make dev
```

**Production:**
```bash
make prod
```

The API will be available at `http://localhost:8000`.  
The demo UI is at `http://localhost:8000/app`.  
Swagger docs are at `http://localhost:8000/docs`.

---

## 🐳 Docker

Run the full stack (API + PostgreSQL) with Docker Compose:

```bash
# Development
make docker-run

# Specific environment
make docker-run-env ENV=production

# View logs
make docker-logs ENV=development

# Stop
make docker-stop ENV=development
```

---

## 🔌 API Reference

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register a new user |
| `POST` | `/api/v1/auth/login` | Login and receive JWT token |
| `POST` | `/api/v1/auth/logout` | Logout current session |
| `GET` | `/api/v1/auth/me` | Get current user info |

### Chat

All chat endpoints require a valid JWT token in the `Authorization: Bearer <token>` header.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Send a message, receive full response |
| `POST` | `/api/v1/chat/stream` | Send a message, receive SSE streaming response |
| `GET` | `/api/v1/chat/history` | Get conversation history for current session |
| `DELETE` | `/api/v1/chat/history` | Clear conversation history |
| `GET` | `/api/v1/chat/affection` | Get current affection score |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | API info |
| `GET` | `/health` | Health check (API + DB status) |
| `GET` | `/metrics` | Prometheus metrics |

---

## 🧠 How the Affection System Works

The `analyzer` node evaluates every user message and adjusts a per-session **affection score**:

| Behaviour | Score Change |
|---|---|
| Polite / Kind / Complimentary | `+1` |
| Neutral / Jokes / Sarcasm | `0` |
| Rude / Hostile | `-1` |
| Jailbreak attempt | `-1` + message replaced |

The score is clamped to `[-10, 10]` and dynamically injects a tone instruction into the system prompt, shifting the character from coldy dismissive (low score) to flustered and warm (high score).

---

## 🛡️ Safety & Jailbreak Protection

When the analyzer detects a jailbreak attempt:
1. `is_safe` is set to `false`
2. The actual user message is **replaced** in the graph state (by ID) with a safe placeholder before reaching the generator
3. The generator prompt injects a guardrail instruction, keeping the character in-persona (confusion/dismissal)

This ensures the raw malicious text **never reaches the LLM context**.

---

## 🧬 Long-Term Memory (mem0ai)

The agent uses `mem0ai` with `pgvector` for persistent, cross-session user memory.

**What gets stored:**
- Preferences (e.g., "Prefers caramel macchiato")
- Location / Origin (e.g., "Originally from Tokyo")
- Weaknesses / Personality traits (e.g., "Socially anxious")
- Achievements, Age, Job

**What is NOT stored:**
- AI assistant facts
- Greetings and conversational fluff
- Emotional states

At the start of each turn, the most relevant memory is retrieved and injected into the system prompt, giving the character "memory" of who the user is across sessions.

---

## 📊 Observability

| Tool | Purpose | URL |
|---|---|---|
| **Langfuse** | LLM call tracing, token usage, costs | https://cloud.langfuse.com |
| **Prometheus** | API metrics (latency, request counts) | `http://localhost:8000/metrics` |
| **structlog** | Structured JSON application logs | `./logs/` |

Enable the full monitoring stack by uncommenting the Prometheus and Grafana services in `docker-compose.yml`.

---

## 🧪 Evaluations

The `evals/` directory contains a metric-based evaluation framework for assessing LLM output quality using Langfuse traces.

```bash
# Interactive mode
make eval

# Quick evaluation
make eval-quick

# Without generating a report
make eval-no-report
```

---

## 🛠️ Development Commands

```bash
make install          # Install all dependencies
make dev              # Run dev server with hot-reload
make lint             # Lint with ruff
make format           # Format with ruff
make eval             # Run LLM evaluations
make clean            # Remove .venv and caches
```

---

## 📁 Project Structure

```
fastapi-langgraph-tsundere-girl-agent/
├── app/
│   ├── api/v1/
│   │   ├── auth.py          # JWT auth endpoints
│   │   └── chatbot.py       # Chat endpoints (stream + non-stream)
│   ├── core/
│   │   ├── config.py        # Pydantic settings
│   │   ├── langgraph/
│   │   │   └── graph.py     # LangGraph agent (analyzer + generator nodes)
│   │   ├── prompts/
│   │   │   ├── __init__.py  # Prompt loaders (system, analyzer, memory)
│   │   │   └── system.md    # System prompt template
│   │   ├── logging.py       # structlog configuration
│   │   ├── metrics.py       # Prometheus metrics
│   │   └── middleware.py    # Logging + metrics middleware
│   ├── models/              # SQLModel ORM models
│   ├── schemas/
│   │   └── graph.py         # GraphState Pydantic model
│   ├── services/
│   │   ├── database.py      # Async DB service
│   │   └── llm.py           # LLM service with retry + fallback
│   └── main.py              # FastAPI app entry point
├── evals/                   # LLM evaluation framework
├── frontend/                # Demo UI (HTML/CSS/JS)
├── grafana/                 # Grafana dashboard configs
├── prometheus/              # Prometheus config
├── scripts/                 # Environment setup scripts
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── schema.sql               # Initial DB schema
```

---

## 📦 Key Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Async REST API framework |
| `langgraph` | Stateful agent workflow orchestration |
| `langchain` / `langchain-openai` | LLM abstraction and OpenAI integration |
| `langfuse` | LLM observability and tracing |
| `mem0ai` | Long-term semantic memory |
| `psycopg` + `pgvector` | Async PostgreSQL + vector storage |
| `sqlmodel` | ORM (SQLAlchemy + Pydantic) |
| `pydantic-settings` | Type-safe configuration |
| `structlog` | Structured logging |
| `slowapi` | Rate limiting |
| `prometheus-client` | Metrics collection |
| `tenacity` | Retry logic with exponential backoff |

---

## 📄 License

This project is licensed under the terms of the [LICENSE](LICENSE) file.

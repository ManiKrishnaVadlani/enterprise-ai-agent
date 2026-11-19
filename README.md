# Enterprise AI Knowledge & Workflow Agent

A full-stack document question-answering application built around a FastAPI service and a React/TypeScript web client. Users can upload PDF and UTF-8 TXT files, search their own indexed documents, ask questions with source citations, and continue saved conversations. The default provider setup runs locally without OpenAI credentials or paid API calls.

This is a small demonstration project. It does not claim production-scale capacity or semantic retrieval accuracy.

## Problem and objectives

Policies, procedures, and other internal documents are hard to search manually. This project explores a traceable workflow for extracting text, finding relevant passages, and returning answers linked to the documents that supplied the evidence.

The implementation aims to:

- Provide an end-to-end local RAG workflow with persistent storage.
- Make document and conversation access user-scoped.
- Keep provider integrations replaceable and testable.
- Return citations from retrieved passages and abstain when evidence is insufficient.
- Keep local demos independent from paid API services.

## Implemented features

- PDF and UTF-8 TXT ingestion, including UTF-8 BOM handling, path-safe filenames, and configurable limits.
- Page-aware PDF extraction and deterministic text chunking with overlap.
- Local deterministic feature-hash embeddings and cosine-similarity retrieval from SQLite.
- Extractive local answers by default; optional Ollama local generation and OpenAI embedding/chat providers.
- Source references with document, chunk, optional page, and relevance-score metadata.
- SHA-256-hashed bearer API tokens, administrator-controlled provisioning, revocation, and user-scoped documents/conversations.
- A fixed agent workflow with three allowlisted read-only tools: knowledge search, document list, and document metadata lookup.
- Bounded conversation history persisted in SQLite; recent user questions may expand follow-up retrieval.
- Request IDs, privacy-conscious logs, process-local metrics, per-user rate limits, and bounded upload concurrency.
- Responsive React/TypeScript interface for token sign-in, documents, assistant chat, conversations, and service status.
- Pytest suite, local RAG evaluation CLI, GitHub Actions checks, Dockerfile, Docker Compose, and Railway volume bootstrap.

## Technology stack

| Area | Implementation |
| --- | --- |
| API | Python 3.14, FastAPI, Pydantic |
| Persistence | SQLite; JSON-encoded vectors with cosine similarity calculated in Python |
| Document processing | pypdf, deterministic character-based chunking |
| Local embeddings | Python standard library feature hashing with BLAKE2b |
| Answer providers | Extractive provider, optional Ollama HTTP API, optional OpenAI chat |
| Hosted embeddings | Optional OpenAI embeddings |
| Frontend | React, TypeScript, React Router, Vite, Tailwind CSS, lucide-react |
| Backend checks | pytest, compileall, GitHub Actions |
| Container | Docker, Docker Compose, gosu-based startup privilege drop |

The OpenAI Python package is included in backend requirements for the optional provider. The default local/extractive path does not itself make OpenAI requests. Ollama and model weights are installed separately when that provider is used.

## Architecture

The backend is a modular monolith: the API, document processing, provider adapters, orchestration, and SQLite store run in one application. The frontend is a separate Vite application that calls the existing API.

High-level request and data flow:

    Browser UI -> FastAPI routes -> authentication and user identity
                                  -> ingestion -> extract -> chunk -> embed -> SQLite
                                  -> RAG -> query embedding -> owner-filtered SQLite search
                                         -> selected answer provider -> validated citations -> response

### Document ingestion and RAG

1. An authenticated client sends raw file bytes with an X-Filename header and application/octet-stream content type.
2. The API reads the request in bounded chunks and enforces the upload limit. The document service validates the filename and file type.
3. TXT is decoded as UTF-8; PDF text is extracted in page order. The original uploaded file is not retained.
4. Extracted text is normalized and divided into bounded chunks. PDF page numbers are retained for citations.
5. The configured embedding provider creates one vector per chunk. Document metadata, chunk text, and vectors are written transactionally to SQLite with the authenticated owner ID.
6. For a question, the same embedding provider vectorizes the query. SQLite filters by owner and optional document ID; Python calculates cosine scores, applies a minimum score, sorts candidates, and returns the top results.
7. Duplicate passages from the same document are suppressed before context assembly. The selected answer provider receives the question and retrieved context.
8. The RAG pipeline returns only source metadata corresponding to source labels cited by the answer. If evidence is missing or source labels are invalid or absent, it returns the no-information response with an empty source list.

### Embeddings and answer modes

| Configuration | Embeddings | Answer generation |
| --- | --- | --- |
| AI_MODE=local, default LLM_PROVIDER | Deterministic local feature hashing | Extractive sentence selection |
| AI_MODE=local, LLM_PROVIDER=ollama | Deterministic local feature hashing | Local Ollama model |
| AI_MODE=openai with no LLM_PROVIDER override | OpenAI embeddings | OpenAI chat |
| Any mode with LLM_PROVIDER=openai | Selected by AI_MODE | OpenAI chat |

The local feature-hash embedder uses normalized word features and adjacent-word features in a fixed 384-dimensional vector by default. It is deterministic and does not download a model, but it is a lightweight lexical approximation: it does not understand meaning, synonyms, or context like a trained embedding model. Hash collisions are possible.

The extractive provider selects up to three sentences based on meaningful question-term overlap and includes source labels. It does not compose or understand new prose and is not equivalent to an LLM. Ollama and OpenAI providers generate text and can still hallucinate; valid source IDs ensure references point to supplied passages but do not prove every statement is entailed by them.

Vectors are stored as JSON text in SQLite and searched with a Python cosine-similarity scan. Search work grows with the number of stored chunks, so the current store is intended for a modest corpus. A relevance score is a ranking signal, not a calibrated confidence percentage. MIN_RELEVANCE_SCORE is the fallback cutoff; separate local and OpenAI overrides are available.

### Agent workflow and tools

The /agent endpoint runs a fixed workflow: one allowlisted knowledge search followed by the existing RAG answer and citation pipeline. The registry exposes three read-only tools:

- knowledge_search returns bounded, owner-scoped passages.
- document_list returns metadata for the authenticated user's documents.
- document_info returns metadata for one owned document, not its contents.

Tool inputs are Pydantic-validated, tool names are allowlisted, and the workflow does not expose shell, arbitrary SQL, filesystem access, or arbitrary code execution. It is controlled orchestration, not an autonomous planning agent.

### Persistence and migrations

SQLite stores users, token hashes, document metadata, chunk text, vectors, and conversation messages. Schema migrations are versioned: migration 1 added users, API tokens, and nullable document ownership; migration 2 added conversations. Existing documents are not assigned to an arbitrary user. Ownerless legacy documents remain stored but are excluded from user-scoped listing/search and return not-found for owner-scoped access.

The database selected by AI_MODE is separate: local mode uses LOCAL_DATABASE_PATH, and OpenAI mode uses DATABASE_PATH. Switching modes does not migrate documents between those files. Back up the active database or Docker volume before changing deployment storage.

## Frontend capabilities

The React single-page application includes:

- **Sign-in:** verifies an administrator-provisioned bearer token against the API. The token is held in browser sessionStorage, sent in the Authorization header, and cleared on logout or an HTTP 401.
- **Overview:** shows document, chunk, and conversation counts plus API readiness.
- **Knowledge base:** uploads PDF/TXT files with progress, lists indexed documents, and deletes owned documents.
- **Assistant:** creates and resumes conversations, submits questions to the agent endpoint, and displays citations returned with new answers.
- **Conversations:** lists, resumes, and deletes the current user's saved conversation history.
- **Settings:** displays API/readiness status and provides session sign-out.
- **Responsive layout:** CSS breakpoints adapt navigation, tables, and chat layout for smaller screens.

The frontend does not create users or API tokens and does not expose provider configuration. Conversation messages are persisted as text; citation objects are not stored, so old answers do not regain citations when history is reloaded. Browser sessionStorage is accessible to JavaScript running on the page, so use a trusted frontend origin and apply deployment-specific browser security protections.

There is no frontend unit or browser end-to-end test suite configured in frontend/package.json. Available frontend checks are TypeScript type checking and a Vite production build.

## Backend API

All routes and schemas are also available from FastAPI's OpenAPI interface at /docs.

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | / | Public | Application status |
| GET | /health | Public | Liveness response |
| GET | /ready | Public | Checks SQLite readiness |
| POST | /documents/upload | Bearer token | Index raw PDF/TXT bytes; requires X-Filename |
| GET | /documents | Bearer token | List the current user's documents |
| DELETE | /documents/{document_id} | Bearer token | Delete an owned document and its chunks |
| POST | /ask | Bearer token | Retrieve passages and return an answer and citations |
| GET | /tools | Bearer token | List allowlisted agent tool schemas |
| POST | /agent | Bearer token | Run the bounded search-and-answer workflow |
| GET, POST | /conversations | Bearer token | List or create conversations |
| GET, DELETE | /conversations/{conversation_id} | Bearer token | Read or delete an owned conversation |
| GET | /metrics | Bearer token | Read process-local aggregate request metrics |

The upload endpoint expects the **raw file body**, not multipart/form-data. The response includes a document ID, filename, ingestion time, and chunk count. Ask/agent responses include answer text and source metadata (document ID, filename, chunk ID, optional PDF page number, and relevance score). POST /agent also returns conversation ID and bounded workflow status metadata.
For example, from PowerShell in the repository root, set the token issued by the provisioning CLI and upload raw bytes:

    $env:AGENT_API_TOKEN = "<paste the provisioned token>"
    curl.exe -X POST "http://127.0.0.1:8000/documents/upload" -H "Authorization: Bearer $env:AGENT_API_TOKEN" -H "X-Filename: handbook.txt" -H "Content-Type: application/octet-stream" --data-binary "@handbook.txt"

Ask a question and inspect the returned answer and source list:

    curl.exe -X POST "http://127.0.0.1:8000/ask" -H "Authorization: Bearer $env:AGENT_API_TOKEN" -H "Content-Type: application/json" -d '{"question":"What does the handbook say about access reviews?"}'

The token shown above is a placeholder. Do not paste a real token into a README, shared terminal transcript, or source file.


## Authentication and security

There is no public registration flow or username/password login. An administrator provisions a user and token through the CLI. Tokens are high-entropy values generated with Python's secrets module, shown once in an interactive terminal, and stored as SHA-256 hashes. The API hashes bearer tokens before lookup, checks token revocation and user activity, and returns 401 for missing or invalid credentials.

Document and conversation reads, searches, and deletes are scoped to the authenticated user in application/database queries. SQLite enables foreign-key enforcement. User-facing errors are mapped to safe HTTP responses; unexpected errors do not return provider internals or document content. Request logs avoid prompts, answers, document text, bearer credentials, and token hashes.

Uploads, PDF pages, extracted text, document chunks, local LLM prompt size, and concurrent uploads have configurable bounds. Rate limiting and metrics are process-local and reset when the service restarts; they do not coordinate across multiple workers or replicas. CORS uses an explicit allowlist and does not allow credentials.

The local Docker Compose service binds port 8000 to host loopback, runs the API as UID/GID 10001, uses a read-only root filesystem, and drops Linux capabilities. The Railway bootstrap uses temporary root permission only when explicitly configured to repair volume ownership; it then re-executes the API as the non-root appuser. This does not replace a deployment-specific security review.

## Project structure

Important files and folders (Python learning examples and generated/cache directories are omitted):

    .
    ├── app/                         # FastAPI application and RAG services
    │   ├── agent.py                 # Bounded agent orchestration
    │   ├── auth.py                  # Bearer-token authentication
    │   ├── config.py                # Environment configuration
    │   ├── document_service.py      # Ingestion, listing, deletion
    │   ├── embeddings.py            # Local and OpenAI embeddings
    │   ├── llm.py                   # Extractive, Ollama, OpenAI answers
    │   ├── rag.py                   # Retrieval, context, citations
    │   ├── routes.py                # HTTP endpoints
    │   ├── tools.py                 # Allowlisted tools
    │   └── vector_store.py          # SQLite persistence and search
    ├── docker/
    │   └── volume-entrypoint.py     # Volume checks and privilege drop
    ├── docs/
    │   ├── architecture.md
    │   ├── demo-guide.md
    │   ├── evaluation.md
    │   └── technical-decisions.md
    ├── evaluation/                   # Labeled RAG evaluation CLI and dataset
    ├── frontend/
    │   ├── src/                      # React pages, API client, styles
    │   ├── package.json
    │   ├── package-lock.json
    │   ├── vite.config.ts
    │   └── README.md
    ├── tests/                        # Backend, storage, provider, learning examples
    ├── .github/workflows/ci.yml     # Backend CI on pushes and pull requests
    ├── .env.example
    ├── frontend/.env.example
    ├── Dockerfile
    ├── docker-compose.yml
    ├── main.py
    ├── pytest.ini
    └── requirements.txt

## Prerequisites

- Python 3.14 and pip.
- Node.js and npm for the web frontend.
- Docker Desktop with Docker Compose for container use.
- Optional: Ollama and a model downloaded separately.
- Optional: an OpenAI API key and account credits if OpenAI providers are selected.

Python package versions are declared in requirements.txt; frontend package versions are managed by frontend/package-lock.json. The repository does not pin a Node version with an engines declaration.

## Local installation and configuration

### Backend

From the repository root in PowerShell:

    py -3.14 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    if (-not (Test-Path .env)) { Copy-Item .env.example .env }

The example environment file selects local mode and contains no usable API key. Keep .env private; it is ignored by Git. For the default no-paid-API workflow, leave AI_MODE=local and LLM_PROVIDER blank or set it to extractive. Do not set LLM_PROVIDER=openai unless you intend to make hosted chat requests.

### Environment variables

The backend loads settings from the process environment and an optional root .env file. These are the application defaults; Docker overrides both database paths to /data.

| Variable | Default | Description |
| --- | --- | --- |
| AI_MODE | local | local selects local embeddings; openai selects OpenAI embeddings and, unless overridden, OpenAI chat. |
| LLM_PROVIDER | derived | extractive, ollama, or openai; local mode defaults to extractive and OpenAI mode defaults to OpenAI. |
| OPENAI_API_KEY | unset | Required for OpenAI embeddings or OpenAI answers. Calls may incur charges. |
| EMBEDDING_MODEL | text-embedding-3-small | OpenAI embedding model name. |
| CHAT_MODEL | gpt-4.1-mini | OpenAI chat model name. |
| OLLAMA_BASE_URL | http://127.0.0.1:11434 | Local Ollama URL; only loopback and host.docker.internal hostnames are accepted. |
| OLLAMA_MODEL | qwen3.5:2b-q4_K_M | Model tag already available to Ollama; the application does not download it. |
| OLLAMA_TIMEOUT_SECONDS | 120 | Request timeout. |
| OLLAMA_TEMPERATURE | 0.1 | Generation temperature, 0–2. |
| OLLAMA_THINK | false | Whether to request separate model reasoning output. |
| OLLAMA_NUM_PREDICT | 512 | Maximum generated tokens (1–4096). |
| OLLAMA_CONTEXT_LENGTH | 4096 | Ollama context setting (512–32768). |
| OLLAMA_MAX_PROMPT_CHARS | 12000 | Maximum combined question/context characters sent to local Ollama. |
| DATABASE_PATH | data/knowledge.db | SQLite file used when AI_MODE=openai. |
| LOCAL_DATABASE_PATH | data/knowledge-local.db | SQLite file used when AI_MODE=local. |
| APP_NAME | Enterprise AI Knowledge & Workflow Agent | Application name in API responses. |
| LOG_LEVEL | INFO | Python logging level. |
| CHUNK_SIZE | 1000 | Maximum chunk length in Unicode characters. |
| CHUNK_OVERLAP | 150 | Character overlap; must be smaller than chunk size. |
| MAX_DOCUMENT_CHUNKS | 10000 | Maximum chunks ingested from one document. |
| TOP_K | 4 | Maximum passages retained by RAG (1–20). |
| MIN_RELEVANCE_SCORE | 0.15 | Fallback cosine-score cutoff (0–1). |
| LOCAL_MIN_RELEVANCE_SCORE | unset | Optional local cutoff overriding MIN_RELEVANCE_SCORE. |
| OPENAI_MIN_RELEVANCE_SCORE | unset | Optional OpenAI cutoff overriding the fallback. |
| MAX_UPLOAD_BYTES | 10485760 | Maximum upload size, 10 MiB. |
| MAX_CONCURRENT_UPLOADS | 2 | Maximum concurrent ingestion requests per process. |
| UPLOAD_WAIT_TIMEOUT_SECONDS | 5 | How long an upload waits for a free processing slot. |
| MAX_PDF_PAGES | 200 | Maximum pages processed from one PDF. |
| MAX_EXTRACTED_TEXT_CHARS | 2000000 | Maximum extracted characters per document. |
| RATE_LIMIT_REQUESTS | 120 | Authenticated requests per user per window. |
| RATE_LIMIT_WINDOW_SECONDS | 60 | Per-user rate-limit window. |
| CORS_ALLOWED_ORIGINS | http://localhost:3000,http://127.0.0.1:3000 | Comma-separated explicit HTTP(S) browser origins. |

### Provision an API token

Run provisioning from an interactive terminal. The plaintext token is displayed once; store it in approved secure storage. The database stores only its hash.

    python -m app.provisioning create-user --display-name "Local user" --label "development"
    python -m app.provisioning revoke --token-id <token-id>

There is no public registration or token-management screen. Creating users/tokens uses the active database selected by the current environment.

### Start the backend

    python -m uvicorn main:app --reload

API docs: http://127.0.0.1:8000/docs
Liveness: http://127.0.0.1:8000/health
Readiness: http://127.0.0.1:8000/ready

### Start the frontend

In a second PowerShell terminal:

    Set-Location frontend
    if (-not (Test-Path .env)) { Copy-Item .env.example .env }.local
    npm ci
    npm run dev

The Vite development server binds to http://127.0.0.1:3000. The frontend example file uses that local API URL and a 10 MiB client upload limit. If you change the frontend origin or backend upload limit, update the backend CORS allowlist or VITE_MAX_UPLOAD_BYTES setting.

Vite variables are shipped to the browser and are not secrets. Do not put API tokens, OpenAI keys, or other private values in VITE_* variables.

To make a frontend production bundle and serve it locally:

    npm run typecheck
    npm run build
    npm run preview

The start script serves dist/ on the platform-provided PORT; it is suitable for a Linux host configured to build the frontend and run its start script. The repository has no frontend Dockerfile or checked-in Railway service configuration.

## Tests and quality checks

Backend tests use pytest. From the repository root:

    python -m pytest -p no:cacheprovider
    python -m compileall -q app tests main.py

HTTP tests are marked with the http marker. If the local Windows/Python environment cannot create the test client's socket pair, run the non-HTTP suite separately with:

    python -m pytest -p no:cacheprovider -m "not http"

The GitHub Actions workflow runs on pushes and pull requests using Python 3.14. It installs backend requirements, compiles app, tests, and main.py, then runs the complete backend test suite on Ubuntu. The frontend has no configured pytest/Jest/Vitest/browser test suite; use npm run typecheck and npm run build for static checks and bundling.

The local evaluation CLI runs a labeled fictional dataset against a temporary SQLite database. By default it uses local feature-hash embeddings and extractive answers, excludes OpenAI, and does not download a model:

    python -m evaluation.run
    python -m evaluation.run --mode retrieval
    python -m evaluation.run --mode answers
    python -m evaluation.run --category answerable --category multi_evidence
    python -m evaluation.run --json-output "$env:TEMP\rag-evaluation.json"

The report contains aggregate retrieval/answer metrics but no retrieved text or generated answer content. To use an already-installed local Ollama provider, run python -m evaluation.run --provider ollama; this requires a running runtime/model and does not download one. The evaluation set is a small smoke/regression dataset, not a general quality benchmark. See [docs/evaluation.md](docs/evaluation.md).

## Docker

Docker Compose runs only the local demo configuration. It binds the API to host loopback, mounts the named agent-data volume at /data, runs the application as UID/GID 10001, uses a read-only root filesystem, a bounded /tmp, drops capabilities, and sets no-new-privileges.

    docker compose config --quiet
    docker compose up --build -d
    docker compose ps
    docker compose logs -f api

Browse to http://127.0.0.1:8000/docs and check readiness at http://127.0.0.1:8000/ready. Stop with docker compose down; the named volume persists. docker compose down -v removes that volume and its database.

### Railway persistent volume

For the backend Docker service, mount a Railway volume at exactly /data and set:

    DATABASE_PATH=/data/knowledge.db
    LOCAL_DATABASE_PATH=/data/knowledge-local.db
    RAILWAY_RUN_UID=0

The Docker entrypoint requires /data to appear as a mount and requires the database paths to match. When the container starts as root under the explicit Railway setting, it changes ownership only for /data and the two recognized SQLite files and their journal/WAL sidecars, verifies write access, and then uses gosu to re-execute itself and Uvicorn as appuser UID/GID 10001. It refuses unexpected symlinks and fails startup if initialization or privilege dropping fails. FastAPI does not run as root. Do not set RAILWAY_RUN_UID=0 if the entrypoint is bypassed.

Mounting /data hides any files previously present at that image path. Back up or migrate existing data before attaching a new volume. The application stores extracted text and vectors in SQLite; it does not preserve the original PDF/TXT upload.

## Railway deployment links

The following URLs were supplied as deployment context. They were not reachable through the available live-check tool during this README review, so their current deployment/readiness status is **not independently verified**:

- Frontend: [sparkling-blessing-production.up.railway.app](https://sparkling-blessing-production.up.railway.app)
- Backend: [enterprise-ai-agent-production-5449bd79.up.railway.app](https://enterprise-ai-agent-production-5449bd79.up.railway.app)
- Backend readiness endpoint: [enterprise-ai-agent-production-5449bd79.up.railway.app/ready](https://enterprise-ai-agent-production-5449bd79.up.railway.app/ready)

Set backend CORS_ALLOWED_ORIGINS to the exact deployed frontend origin when enabling cross-origin browser requests. Railway variables and service settings are configured outside this repository; no Railway manifest is checked in. Confirm the deployment's volume, environment variables, logs, health checks, and HTTPS behavior in Railway before relying on these links.

## Current implementation status

| Area | Status |
| --- | --- |
| Local backend workflow | Implemented: upload, extraction, chunking, local embeddings, SQLite, retrieval, extractive answers, citations |
| Optional providers | Implemented: Ollama local chat and OpenAI embeddings/chat; live use requires separately configured services/credentials |
| User isolation | Implemented: token-authenticated, owner-scoped document and conversation operations |
| Agent | Implemented as a fixed one-search workflow over three read-only tools; no arbitrary action execution |
| Conversations | Implemented with owner-scoped SQLite persistence and bounded recent user-question retrieval context |
| Frontend | Implemented as a React/TypeScript browser client for existing API operations |
| Evaluation | Implemented as a small local labeled-data smoke/regression tool |
| Container and Railway volume bootstrap | Configuration and startup logic are present; actual image build and live volume behavior need verification in the target environment |
| Live Railway URLs | Provided as context; not independently verified during this review |

## Limitations and future improvements

Current limitations:

- Only text-based PDF and UTF-8 TXT are supported. OCR, Office formats, HTML, and image-only PDFs are not implemented.
- Local feature-hash vectors are lexical rather than semantic; synonym and paraphrase retrieval may be weak.
- SQLite vectors are scanned in Python. There is no dedicated vector index or distributed database layer.
- OpenAI and Ollama generation can produce unsupported text. Citation validation checks source references, not semantic entailment.
- Rate limiting and metrics are process-local, reset on restart, and not shared across workers.
- There is no background ingestion queue, streaming answer interface, malware scanning, feedback capture, or browser end-to-end testing.
- The fixed agent can search and read metadata; it does not perform writes or actions in external business systems.
- User and token administration is CLI-only. No account registration, password login, token issuance UI, or token refresh flow exists.
- Conversation retention is user-managed; automatic expiration and history summarization are not implemented.
- Production hosting hardening (including TLS termination, browser security headers/CSP, backups, monitoring, and capacity validation) depends on the deployment and is not established by this repository alone.

Possible future work, subject to demonstrated need:

- Evaluate retrieval changes on a larger independently labeled dataset before adjusting scoring.
- Add OCR or asynchronous ingestion for suitable document volumes and formats.
- Consider PostgreSQL/pgvector and shared rate limiting if the application outgrows one-process SQLite behavior.
- Add retention, backup/restore, and operational monitoring policies.
- Add browser-level frontend tests and deployment-specific security headers.

## Technical documentation

- [Architecture](docs/architecture.md)
- [Technical decisions](docs/technical-decisions.md)
- [Local demo guide](docs/demo-guide.md)
- [RAG evaluation guide](docs/evaluation.md)
- [Frontend setup guide](frontend/README.md)

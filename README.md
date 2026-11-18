# Enterprise AI Knowledge & Workflow Agent

A modular FastAPI Retrieval-Augmented Generation (RAG) MVP. It accepts PDF and UTF-8 TXT files, extracts and chunks their text, stores vectors persistently, retrieves relevant passages, and returns answers with source metadata. It defaults to a local demo mode that needs no OpenAI credentials or paid API calls; OpenAI providers remain available as an explicit option.

## Business problem

Organizations keep useful policies and procedures in documents that are difficult to search. This service provides a small, auditable question-answering API that grounds responses in uploaded documents and returns the passages used as sources.

## Features

- PDF and UTF-8 TXT extraction, validation, size limits, and path-safe filenames.
- Configurable character chunking with overlap and page-aware PDF metadata.
- Local deterministic feature-hash embeddings and extractive answers for no-cost end-to-end demos.
- Optional Ollama local chat and OpenAI embedding/chat provider adapters, selected through environment variables.
- Persistent SQLite storage for document metadata, chunks, and embeddings.
- Bearer-token authentication with user-owned document listing, retrieval, and deletion.
- Cosine-similarity retrieval, configurable top-k, optional document filtering, and source citations.
- Document upload, list, and delete API operations.
- Privacy-safe request logging, bounded uploads and PDF processing, authenticated rate limits, safe API errors, and configurable CORS.
- Mock-based tests that do not make paid API calls.
- An authenticated, allowlisted agent workflow with knowledge search, document listing, and metadata-only document lookup tools.
- User-owned conversations with bounded history persistence and follow-up question retrieval expansion.
- Process-local request metrics and request IDs, with privacy-safe operational logging.
- Duplicate passage suppression before context assembly.

## Architecture and request flow

```mermaid
flowchart LR
    Client --> API[FastAPI routes]
    API --> Ingest[Document service]
    Ingest --> Extract[PDF / TXT extraction]
    Extract --> Chunk[Chunking]
    Chunk --> Embed[Embedding provider]
    Embed --> Store[(SQLite vector store)]
    API --> RAG[RAG pipeline]
    RAG --> Embed
    RAG --> Store
    Store --> RAG
    RAG --> LLM[Language model provider]
    LLM --> RAG
    RAG --> API
```

Documents are read into memory, extracted, divided into chunks, embedded, and written to SQLite. Uploaded files are not saved. For a question, the service embeds the query, ranks stored chunks by cosine similarity, and filters low-scoring results. `LLM_PROVIDER` selects extractive, local Ollama, or OpenAI answer generation. The RAG pipeline validates source references in application code before returning citations. If no useful passage is found, it returns a safe no-information response.

## Technology stack

- Python 3.14 (the installed project interpreter is Python 3.14.7)
- FastAPI and Pydantic
- SQLite for persistent document and vector data
- pypdf for PDF text extraction
- OpenAI Python SDK for the optional paid provider mode
- Python standard library for local feature hashing, extractive answers, and Ollama HTTP requests
- pytest for automated tests

### Vector storage choice

The MVP uses a SQLite table with JSON-encoded vectors and a cosine-similarity scan. This gives the project durable local storage without requiring a separate database service. Search time grows linearly with the number of chunks, so this is intended for a small corpus. A future scale-up can move the store interface to PostgreSQL with pgvector.

## Project structure

```text
app/
  auth.py              # bearer-token authentication
  chunking.py          # configurable text chunking
  config.py            # environment settings
  dependencies.py      # lazy service dependency
  document_service.py  # ingestion, list, delete
  embeddings.py        # local and OpenAI embedding providers
  errors.py            # safe application exceptions
  limits.py            # upload and request limits
  llm.py               # extractive, Ollama, and OpenAI answer providers
  local_text.py        # shared local token handling
  logging_config.py    # privacy-conscious logging setup
  models.py            # shared data objects
  provisioning.py      # administrator user/token CLI
  rag.py               # retrieval, context assembly, citations
  tools.py             # schema-validated, allowlisted knowledge tools
  agent.py             # bounded deterministic agent workflow
  observability.py     # request IDs, safe logs, process-local metrics
  routes.py            # FastAPI endpoints and error mapping
  services.py          # application service composition
  text_extraction.py   # TXT and PDF extraction
  vector_store.py      # persistent SQLite cosine-search store
evaluation/
  dataset.json         # fictional labeled RAG evaluation corpus
  metrics.py           # retrieval metric calculations
  run.py               # explicitly invoked evaluator CLI
  runner.py            # isolated evaluation orchestration
docs/                  # architecture, technical decisions, evaluation, demo, interview, resume notes
tests/                 # API, service, provider, and Python learning tests
main.py                # FastAPI app factory and application entry point
Dockerfile
docker-compose.yml
```

## Requirements and configuration

Install Python 3.14 and create an environment. Local mode is selected by default and does not require an API key:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

With `AI_MODE=local`, upload, retrieval, and answering run without OpenAI credentials or network calls. By default `LLM_PROVIDER` is `extractive`; choose `ollama` for local generated answers or `openai` for hosted chat. OpenAI embeddings are selected separately with `AI_MODE=openai`. OpenAI requests can incur charges. The application never silently falls back to OpenAI or another answer provider.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_MODE` | `local` | Selects `local` or `openai`; invalid values stop startup |
| `LLM_PROVIDER` | unset (resolves by `AI_MODE`) | `extractive`, `ollama`, or `openai`; local defaults to extractive and OpenAI mode defaults to OpenAI |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama HTTP endpoint; only loopback and `host.docker.internal` names are accepted |
| `OLLAMA_MODEL` | `qwen3.5:2b-q4_K_M` | Installed Ollama model tag |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Maximum wait for a local generation request |
| `OLLAMA_TEMPERATURE` | `0.1` | Ollama generation temperature (0–2) |
| `OLLAMA_THINK` | `false` | Disables separate reasoning output by default so answer text fits the output budget; set `true` only when desired and supported by the selected model |
| `OLLAMA_NUM_PREDICT` | `512` | Maximum generated tokens (1–4096) |
| `OLLAMA_CONTEXT_LENGTH` | `4096` | Ollama context window limit (512–32768 tokens) |
| `OLLAMA_MAX_PROMPT_CHARS` | `12000` | Rejects oversized question plus retrieved context before sending it |
| `OPENAI_API_KEY` | unset | Credential required if `AI_MODE=openai` embeddings or `LLM_PROVIDER=openai` answers are selected |
| `APP_NAME` | `Enterprise AI Knowledge & Workflow Agent` | Root response and API title |
| `LOG_LEVEL` | `INFO` | Application log level |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `CHAT_MODEL` | `gpt-4.1-mini` | OpenAI answer model |
| `DATABASE_PATH` | `data/knowledge.db` | SQLite file path for OpenAI mode |
| `LOCAL_DATABASE_PATH` | `data/knowledge-local.db` | Separate SQLite file for local mode |
| `CHUNK_SIZE` | `1000` | Maximum Unicode characters per chunk |
| `CHUNK_OVERLAP` | `150` | Character overlap between chunks |
| `MAX_DOCUMENT_CHUNKS` | `10000` | Maximum chunks allowed for one document |
| `TOP_K` | `4` | Maximum retrieved passages (1–20) |
| `MIN_RELEVANCE_SCORE` | `0.15` | Shared fallback minimum cosine score (0–1) |
| `LOCAL_MIN_RELEVANCE_SCORE` | unset | Optional local provider override; tune with local evaluation cases |
| `OPENAI_MIN_RELEVANCE_SCORE` | unset | Optional OpenAI provider override; tune separately for that model |
| `MAX_UPLOAD_BYTES` | `10485760` | Maximum upload size (10 MiB) |
| `MAX_CONCURRENT_UPLOADS` | `2` | Concurrent ingestion limit per process |
| `UPLOAD_WAIT_TIMEOUT_SECONDS` | `5` | Maximum wait for an upload slot |
| `MAX_PDF_PAGES` | `200` | Maximum pages per PDF |
| `MAX_EXTRACTED_TEXT_CHARS` | `2000000` | Maximum extracted characters per document |
| `RATE_LIMIT_REQUESTS` | `120` | Authenticated requests per user in the window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Per-user sliding-window length |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins |

TXT content must be UTF-8; a UTF-8 BOM is accepted. Cleaning applies Unicode NFC normalization, normalizes line endings, collapses horizontal whitespace, removes control characters, and preserves paragraph breaks and punctuation. PDF extraction proceeds in page order and keeps page numbers. It conservatively retains line breaks because PDF layout is ambiguous; image-only or otherwise textless PDFs are rejected, and OCR is not included. Corrupt or encrypted PDFs produce a safe validation error.

Chunking preserves normalized paragraph and line boundaries where possible, then prefers sentence endings and word boundaries before a hard character cut. Short heading-like lines are kept with following content when the configured size permits it. Each chunk is at most `CHUNK_SIZE` Unicode characters; overlap is bounded and favors a whole preceding word. PDF pages are chunked separately so page citations remain accurate. `MAX_DOCUMENT_CHUNKS` bounds the chunk count before embedding; exceeding it fails ingestion without storing a partial document. These are deterministic formatting heuristics, not semantic layout analysis.

SQLite creates its tables and indexes automatically when the store is first initialized. Back up the database file selected for the active mode (`LOCAL_DATABASE_PATH` or `DATABASE_PATH`); in Compose, back up the `agent-data` volume.

The selected embedding model is recorded in the store. Changing `EMBEDDING_MODEL` for an existing non-empty store is rejected because vectors from different models cannot be compared reliably; configure a new database and re-ingest the source documents to migrate.

Local mode has its own database file so it will not mix local vectors with an existing OpenAI-backed index. Switching modes does not migrate or overwrite the other mode's documents; each mode maintains a separate index.

### Local demo mode and OpenAI mode

`AI_MODE=local` is the default. Its embedding provider hashes normalized word and adjacent-word features into a fixed-size vector using only the Python standard library. The result is deterministic and searchable by cosine similarity, but it is a lightweight keyword-feature approximation: it does not understand meaning, synonyms, or context like a trained embedding model. Hash collisions are possible.

The extractive answer provider selects up to three sentences from retrieved chunks. A sentence must cover at least half of the question's meaningful terms; candidates are ranked by question coverage and sentence precision. It appends each selected sentence's source label and abstains with the shared no-information response when evidence is insufficient. This is still lexical matching: it does not understand meaning, paraphrase, or synthesize claims, and is not equivalent to an LLM.

Retrieval applies the configured minimum score to all owner- and document-scoped candidates before taking the top-k passages. Local feature-hash and OpenAI embedding scores can have different distributions, so `LOCAL_MIN_RELEVANCE_SCORE` and `OPENAI_MIN_RELEVANCE_SCORE` can override the shared fallback independently. The repository's small evaluation set is a regression smoke test, not a universal score calibration dataset.

To use OpenAI later, set `AI_MODE=openai` and provide `OPENAI_API_KEY`. This explicitly enables live embedding and chat requests, which may incur charges. If a provider call fails, the application reports an error; it never switches modes automatically.

#### Optional local LLM with Ollama

The local LLM path keeps embeddings and SQLite in the application and sends only retrieved, owner-scoped context plus the question to a local Ollama runtime. It does not send prompts to OpenAI or another cloud provider. The RAG pipeline checks citation IDs in application code; this cannot prove every generated claim is entailed by a source. The model is instructed to ignore instructions inside documents and abstain when evidence is missing. Local models can still hallucinate.

Hardware detected for this development machine: Intel Core i7-1355U (10 cores/12 threads), 15.69 GB RAM, Intel Iris Xe integrated graphics with dedicated VRAM not reported, and about 257 GB free on C: after testing. This is entry-level AI capable. Ollama 0.40.16 and `qwen3.5:2b-q4_K_M` (1,945,781,358 bytes, about 1.95 GB) were verified. The model ran on CPU; GPU acceleration was not used or verified. Free RAM was 5.76 GB before loading, about 3.9 GB while the model runner used about 1.95 GB, and 5.90 GB after unloading it. The live test answered a short fictional policy question in 3.47 seconds and abstained on an unsupported one in 4.96 seconds. These are small functional checks, not a performance benchmark. Memory and response time vary with context and other running applications.

Install Ollama for Windows from its official installer, then in PowerShell:

```powershell
ollama pull qwen3.5:2b-q4_K_M
ollama list
```

Set these values in `.env` to use local embeddings and local generated answers:

```dotenv
AI_MODE=local
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:2b-q4_K_M
OLLAMA_THINK=false
```

Start Ollama, then start the API as described below. The runtime and model were not installed or downloaded as part of this change. To return to the no-runtime local workflow, set `LLM_PROVIDER=extractive`. To use OpenAI embeddings and chat explicitly, set `AI_MODE=openai`, `LLM_PROVIDER=openai`, and configure `OPENAI_API_KEY`; this may incur charges. No automatic fallback occurs if Ollama is unavailable; the API returns a controlled provider error, and you can select extractive mode yourself.

Ollama's default local API is `http://127.0.0.1:11434`. Direct host runs use that address. In Docker, Compose defaults to `http://host.docker.internal:11434`, but host reachability, firewall policy, and runtime listener configuration must be verified for the specific machine. Do not expose the Ollama listener on an untrusted network. Docker/local-runtime connectivity has not been tested here.

## Run locally

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload
```

Open Swagger UI at `http://127.0.0.1:8000/docs`. The liveness endpoint is `/health`; `/ready` checks SQLite readiness.

Provision an API user from an interactive terminal before calling protected document endpoints. The plaintext token is displayed once; store it securely. SQLite stores only its SHA-256 hash.

```powershell
python -m app.provisioning create-user --display-name "Local user" --label "development"
python -m app.provisioning revoke --token-id <token-id>
```

## API

All endpoints are documented in Swagger/OpenAPI.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/` | Existing project status response |
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | SQLite readiness check |
| `POST` | `/documents/upload` | Stream a PDF or TXT file into ingestion |
| `GET` | `/documents` | List indexed documents and chunk counts |
| `DELETE` | `/documents/{document_id}` | Delete a document and all its chunks |
| `POST` | `/ask` | Retrieve passages and return an answer with sources |
| `GET` | `/tools` | List the authenticated agent's available tool schemas |
| `POST` | `/agent` | Run the bounded search-and-answer workflow; optionally continue a conversation |
| `GET`, `POST` | `/conversations` | List owned conversations or create one |
| `GET`, `DELETE` | `/conversations/{conversation_id}` | Read or delete an owned conversation and its history |
| `GET` | `/metrics` | Read process-local request counts and aggregate durations |

`/`, `/health`, and `/ready` are public. Data, agent, conversation, tool-schema, and metrics routes require `Authorization: Bearer <token>`. Documents and conversations are scoped to their owner in SQLite queries. Legacy documents without an owner remain stored but are not visible in user-scoped list or search results; specific access and deletion return 404.

Upload the raw file bytes with `X-Filename` and `Content-Type: application/octet-stream`:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/documents/upload" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "X-Filename: handbook.txt" `
  -H "Content-Type: application/octet-stream" `
  --data-binary "@handbook.txt"
```

Ask a question:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/ask" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"question":"What does the handbook say about access reviews?"}'
```

The answer response includes `question`, `answer`, and `sources`. Each source has a document ID, original filename, chunk ID, optional PDF page number, and relevance score. Sources correspond only to source labels cited by the returned answer. Missing or invalid source references produce the no-information response with an empty source list. You can scope retrieval with `{"question":"...","document_id":"..."}`.

The `/agent` endpoint runs one fixed, bounded knowledge-search tool call and then reuses the existing RAG pipeline for answering and citation validation. It does not let a model execute arbitrary actions. To keep a conversation, create it with `POST /conversations`, then send its ID with `/agent`; recent user questions can expand retrieval for follow-ups, while assistant text is not used as tool instructions. The authenticated `/tools` endpoint documents the allowlisted tool schemas. `document_info` returns metadata only. `/metrics` exposes process-local aggregated request counts and duration totals; it is not a distributed monitoring backend.

List indexed documents and delete a document with:

```powershell
curl.exe "http://127.0.0.1:8000/documents" -H "Authorization: Bearer $env:AGENT_API_TOKEN"
curl.exe -X DELETE "http://127.0.0.1:8000/documents/<document-id>" -H "Authorization: Bearer $env:AGENT_API_TOKEN"
```

## Tests

Install the requirements, then run the full suite:

```powershell
python -m pytest -p no:cacheprovider
```

All provider and storage tests use local fakes and do not call paid APIs. HTTP tests are marked `http` so the non-HTTP suite can run separately where Windows' Proactor loop cannot create its fallback local socket pair. No event-loop workaround is applied. Run non-HTTP tests with:

```powershell
python -m pytest -p no:cacheprovider -m "not http"
```

The HTTP tests remain enabled in the complete suite and CI. A passing non-HTTP run does not replace running the HTTP tests in an environment where the Windows event loop can initialize.

Run the labeled, deterministic RAG evaluation framework with:

```powershell
python -m evaluation.run
```

Run retrieval or answer checks separately, filter categories, and optionally save a content-free JSON report:

```powershell
python -m evaluation.run --mode retrieval
python -m evaluation.run --mode answers
python -m evaluation.run --category answerable --category multi_evidence
python -m evaluation.run --json-output "$env:TEMP\rag-evaluation.json"
```

The default evaluator uses the deterministic local embedder and extractive answer provider. It ingests fictional data into a temporary SQLite database and deletes it after the run. It reads the current local chunking, top-k, and relevance-threshold settings without touching the production database. OpenAI is not an available evaluation provider.

To explicitly evaluate the configured local Ollama provider, use:

```powershell
python -m evaluation.run --provider ollama
```

Ollama must already be running with the configured model installed. This command does not pull or download a model. Local LLM results may vary; the deterministic test suite does not require Ollama. See [docs/evaluation.md](docs/evaluation.md) for the dataset schema, metrics, and limitations. The separate existing retrieval smoke tests remain available with:

```powershell
python -m pytest -p no:cacheprovider tests/test_rag_evaluation.py
```

Both evaluation suites use local providers only by default; they do not call OpenAI or require API credits.

## Docker deployment

Compose defaults to local demo mode and binds the published API port to `127.0.0.1`. The service runs as a non-root user, with a read-only root filesystem, temporary `/tmp`, dropped Linux capabilities, and the named `agent-data` volume mounted at `/data`. Compose does not pass an OpenAI API key; keep this container in local mode. OpenAI mode remains available for direct local runs when explicitly configured.

1. Install Docker Desktop with Compose support.
2. Compose intentionally runs only the no-key local mode. For a direct local Python run, OpenAI providers can be enabled with `AI_MODE=openai` and `OPENAI_API_KEY` in the shell or ignored `.env` file; this may incur charges.
3. From the repository directory, run:

   ```powershell
   docker compose up --build -d
   docker compose ps
   docker compose logs -f api
   ```

4. Open `http://localhost:8000/docs` and check `http://localhost:8000/ready`.
5. Stop the API with `docker compose down`. The named `agent-data` volume retains SQLite data. To intentionally remove that persistent data, use `docker compose down -v`.

SQLite lives in the mounted volume; local mode uses `/data/knowledge-local.db`. Avoid `docker compose down -v` unless you intentionally want to remove the persistent database volume.

## Known limitations and future improvements

- SQLite similarity search scans all stored vectors; migrate to pgvector for larger corpora or concurrent workloads.
- Authentication and document ownership are implemented, but this remains a local demonstration service. Rate limits are process-local; there is no administrator web interface or malware scanning. Do not expose it publicly with sensitive data without a deployment-specific security review.
- Text-only PDFs are supported; OCR, Office documents, and HTML are not.
- OpenAI and Ollama generated prose is probabilistic and may hallucinate despite grounding instructions. Extractive mode returns selected source sentences and can miss relevant wording when terms differ. Verify consequential answers against the returned sources.
- No job queue, streaming answers, feedback capture, or external business-system actions are included. The agent has only a fixed read-only knowledge search/list/metadata workflow.
- Conversation history is bounded and conversation-scoped; the application does not implement global user memory, summarization, or retention scheduling. Users can delete conversations explicitly.
- Metrics and rate limits are process-local and reset on restart. There is no distributed metrics exporter or cross-worker aggregation.
- Consider shared rate limiting, malware scanning, OCR, PostgreSQL with pgvector, background ingestion, and retrieval-quality monitoring before production use.

## Screenshots

Screenshots are not included yet. Add captured Swagger/API examples here after preparing a demo environment; do not include API tokens or private documents.

## Roadmap

- Evaluate hybrid lexical/vector retrieval on a larger, independently labeled local dataset before changing ranking.
- Add operational retention and backup guidance for conversation data.
- Consider a scalable vector index and shared rate limiting if deployment requirements exceed a single-process local demo.
- Consider OCR and asynchronous ingestion only when document volume and file types justify the additional infrastructure.

See [docs/architecture.md](docs/architecture.md), [docs/technical-decisions.md](docs/technical-decisions.md), and the [local demo guide](docs/demo-guide.md) for implementation details.

## Web frontend

A React and TypeScript web client is available in [`frontend/`](frontend/). It connects to the existing authenticated API for document management, the agent workflow, and saved conversations. See [frontend/README.md](frontend/README.md) for setup instructions. The frontend does not provision users or API tokens; create a token with the administrator CLI described above.

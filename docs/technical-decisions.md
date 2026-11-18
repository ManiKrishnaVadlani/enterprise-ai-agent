# Technical Decisions

This document explains the decisions reflected in the current implementation. It is based on the source, configuration, tests, container files, and [`architecture.md`](architecture.md). The repository does not preserve a formal decision history for every choice, so reasoning below describes the benefits supported by the implementation rather than claiming that a historical comparison took place. Alternatives are identified as documented, general, or not recorded.

## 1. FastAPI for the HTTP application

### Context/problem

The project needs HTTP endpoints for health checks, document ingestion and management, and question answering. Request validation and a discoverable API schema are also useful for clients.

### Decision

The application is implemented with FastAPI. `main.py` creates the app, and `app/routes.py` declares the endpoints and their request and response models.

### Reasoning

The implementation uses FastAPI route declarations, dependency injection for lazily built services, middleware for CORS, and generated OpenAPI documentation. The upload route documents its raw binary request body. The framework also provides the `TestClient` interface used in HTTP tests.

### Advantages

- Routes and their response models are defined near each other.
- OpenAPI makes endpoint contracts discoverable.
- Dependency injection allows tests to supply isolated services.
- Async request streaming is available for the upload body.

### Trade-offs

- The app depends on FastAPI and its ASGI stack, including Starlette.
- Framework features do not provide authentication, authorization, or deployment by themselves; those are outside the current implementation.

### Alternatives considered

The repository does not record a formal framework comparison. Flask and Django are general Python web-framework alternatives, but this project does not implement or benchmark them.

## 2. Pydantic request and response models

### Context/problem

HTTP input must be validated, and response data should have a stable, documented shape.

### Decision

The route layer uses Pydantic models for API request and response data. For example, `AskRequest` constrains question length and rejects whitespace-only questions; `AskResponse`, `DocumentResponse`, and other response models define output fields.

### Reasoning

FastAPI integrates these models into request validation and OpenAPI schema generation. Response models also serialize the API's data objects into the declared field shapes.

### Advantages

- Invalid question payloads are rejected at the HTTP boundary.
- API inputs and outputs have explicit schemas.
- The generated OpenAPI document reflects these contracts.

### Trade-offs

- Models and constraints must be updated when the API contract changes.
- Pydantic validation does not replace domain checks such as filename validation, file-size enforcement, or provider configuration checks.

### Alternatives considered

No alternative validation library is recorded. Manual validation is a general alternative, but the current route implementation uses Pydantic models and validators.

## 3. SQLite for document and vector storage

### Context/problem

The service needs persistent storage for documents, chunks, source metadata, and embeddings, while supporting local runs without a separate database service.

### Decision

`SQLiteVectorStore` stores the data in SQLite. The database has `documents`, `chunks`, and `store_metadata` tables. Compose mounts the database directory under `/data` on the named `agent-data` volume.

### Reasoning

SQLite provides persistence in a database file and is available to the Python application without operating another service. The README describes this choice as fitting the local MVP; the Compose volume preserves the file across container recreation.

### Advantages

- Local setup does not require a database server.
- Transactions, foreign keys, and indexes are provided by SQLite.
- Document deletion cascades to chunks through the configured foreign key.
- A named Docker volume can retain the database independently of the container.

### Trade-offs

- SQLite is a single-file database and this application does not implement a distributed storage layer.
- Search computes scores in application code, so the current design is intended for a small corpus and modest workload.
- A shared database file does not provide application-level tenant or document authorization.

### Alternatives considered

The README identifies PostgreSQL with pgvector as a possible future scale-up path. The repository does not contain a formal benchmark or migration implementation, and it does not claim that pgvector has been evaluated against this store.

## 4. JSON vectors and Python cosine search in SQLite

### Context/problem

The app must persist vectors and rank stored chunks against a question vector. The current setup does not use a dedicated vector database or vector extension.

### Decision

Vectors are serialized as JSON in the `chunks.embedding` column. `SQLiteVectorStore.search()` loads the selected rows, calculates cosine similarity in Python, sorts by score, and returns the top results. Optional `document_id` filtering is applied in the SQL query.

### Reasoning

This keeps the storage implementation within the existing SQLite database and makes the scoring process explicit in application code. The implementation validates finite values, consistent dimensions, and recorded model metadata before comparing vectors.

### Advantages

- No vector extension or separate search service is required.
- Stored chunks and their vectors share the same transaction and document lifecycle.
- The cosine calculation is directly covered by focused store tests.

### Trade-offs

- Each search reads and scores candidate vectors in Python; work grows linearly with the number of selected chunks.
- JSON is simple to inspect but is not a specialized numeric vector representation.
- This approach is not intended for large corpora or demanding concurrent search workloads.

### Alternatives considered

The architecture documentation and README mention pgvector as a future option. A dedicated vector database or another database with a vector index are general alternatives; no such implementation or formal comparison exists in this repository.

## 5. Local feature-hash embeddings and extractive answers

### Context/problem

The project needs a complete local RAG path that can be demonstrated without credentials, paid API usage, or downloading an embedding model.

### Decision

`AI_MODE=local` is the default. `LocalEmbeddingProvider` creates normalized fixed-size vectors from hashed word and adjacent-word features using the standard library. `ExtractiveAnswerProvider` selects up to three sentences only when each covers at least half of the question's meaningful terms, ranks the candidates by coverage and sentence precision, then appends source labels.

### Reasoning

These providers run within the application and require no model download or OpenAI request. The tests verify deterministic vectors and exercise upload, retrieval, source labels, and deletion while explicitly rejecting an OpenAI import in the local workflow.

### Advantages

- The end-to-end demo works without an API key or paid provider call.
- Embeddings are deterministic for the same text and implementation version.
- Answers are copied from retrieved sentences rather than composed as new prose.
- No additional ML package or model artifact is needed.

### Trade-offs

- Hashed lexical features do not represent semantic meaning and may fail when the question and document use different words.
- Hash collisions can occur.
- Extractive selection does not paraphrase, synthesize across passages, or perform general language-model reasoning.
- The local answer can return no information even when a person might recognize related wording.

### Alternatives considered

OpenAI-backed embeddings and chat are implemented as an opt-in mode. Downloaded local embedding models or other local language models are general alternatives, but they would add model files, runtime requirements, or dependencies and are not implemented here.

## 6. Optional OpenAI embedding and chat providers

### Context/problem

The local demo is intentionally lightweight, while the application also needs a path to use externally hosted embedding and answer models.

### Decision

`AI_MODE=openai` wires `OpenAIEmbeddingProvider` and `OpenAILanguageModel` into the same ingestion and RAG services. It uses the configured embedding and chat model names and requires `OPENAI_API_KEY` when making provider requests.

### Reasoning

The OpenAI adapters implement the same provider interfaces as local mode. Client creation is lazy, and the embedding adapter batches texts, checks response counts and dimensions, and configures timeouts and retries. The chat system instruction asks the model to use only retrieved context and cite source labels.

### Advantages

- The application can use hosted semantic embeddings and generated answers without changing its route or storage workflow.
- Provider errors are translated into application errors and safe HTTP responses.
- OpenAI remains opt-in, so local operation does not require credentials.

### Trade-offs

- Requests require credentials, network availability, and may incur charges.
- Generated answers are probabilistic and the prompt cannot guarantee correctness.
- Stored vectors are tied to an embedding model. The store rejects a model change for a non-empty index, so changing models requires a separate database or re-ingestion.

### Alternatives considered

The local providers are the implemented no-cost alternative. Other hosted provider vendors are general alternatives, but no other vendor adapter is present or documented as evaluated.

## 7. Provider abstractions for embeddings and answers

### Context/problem

The ingestion and RAG flows need to work with different embedding and answer implementations without duplicating the workflows.

### Decision

`EmbeddingProvider` and `LanguageModelProvider` are Python protocols. `build_services()` chooses concrete providers according to `Settings.ai_mode`; `DocumentService` and `RAGPipeline` receive those providers through constructor injection.

### Reasoning

Both local and OpenAI implementations satisfy the same small method contracts. Tests can inject fakes or select a provider directly without changing route code or the storage workflow.

### Advantages

- Provider selection is centralized in service composition.
- Local and OpenAI modes share ingestion and retrieval orchestration.
- Unit tests can verify pipeline behavior without making paid API calls.
- Additional implementations can follow the existing protocol shape.

### Trade-offs

- The abstraction covers only the operations currently used; provider-specific capabilities are not represented.
- Implementations still need compatible vector dimensions and model metadata for a given database.
- Provider switching does not migrate existing vectors or make different embedding spaces comparable.

### Alternatives considered

Directly calling OpenAI from the route or document service is a general simpler alternative, but it would couple those components to a vendor and does not match the current protocol-based design. No alternative dependency-injection framework is used.

## 8. Character chunking with configurable overlap

### Context/problem

Documents can be longer than the passages that should be embedded and retrieved as individual units. Splitting text also limits the context sent to the answer provider.

### Decision

`chunk_text()` divides normalized text into character-sized windows, preferring word boundaries where possible. `CHUNK_SIZE` defaults to 1000 characters and `CHUNK_OVERLAP` defaults to 150 characters. Settings validate that the chunk size is positive and overlap is non-negative and smaller than the chunk size.

### Reasoning

Overlap repeats some text between neighboring chunks, reducing the chance that a useful phrase near a boundary is separated from the surrounding context. PDF pages are chunked separately so each chunk retains the page number used for source attribution.

### Advantages

- Chunking bounds the size of each embedded and retrieved text passage.
- Overlap can preserve continuity across adjacent chunks.
- Chunk size and overlap can be changed through environment settings.
- Page-aware processing retains PDF page metadata.

### Trade-offs

- Character windows are not based on token counts, so they do not precisely control model token usage.
- Overlap duplicates text, which increases the number of stored chunks and can create repeated retrieval results.
- Fixed defaults may not suit every document type or question style.

### Alternatives considered

The repository implements character-based chunking only. Token-based or structure-aware splitting are general alternatives; no benchmark or alternative splitter is included.

## 9. Docker and Docker Compose

### Context/problem

The app needs a repeatable container definition and a way to run it with its persistent database while keeping local demo configuration straightforward.

### Decision

The Dockerfile builds from `python:3.14-slim`, installs the pinned requirements, runs as a non-root user, and starts Uvicorn. Docker Compose maps host loopback port 8000 to the container, supplies local-mode settings, and mounts the named `agent-data` volume at `/data`. The Compose container uses a read-only root filesystem, a bounded temporary filesystem, drops Linux capabilities, and enables `no-new-privileges`.

### Reasoning

The Dockerfile captures the runtime and startup command. Compose captures the local service configuration, port binding, and persistent data mount. The container health check calls `/ready`.

### Advantages

- The container includes a defined Python runtime and application dependencies.
- The process runs as a non-root user with reduced container privileges.
- The named volume keeps SQLite data outside the container lifecycle.
- Binding the published port to `127.0.0.1` limits host exposure to the local machine.

### Trade-offs

- Docker must be installed to build and run the container.
- A persistent volume requires deliberate backup and lifecycle management.
- Loopback binding is intended for local use and does not expose the service for remote clients.
- The repository configuration alone does not prove that an image builds or that a deployment is production-ready.

### Alternatives considered

Running Uvicorn directly in a Python virtual environment is documented as a local alternative. No other container runtime or deployment platform is configured in the repository.

## 10. Automated tests and CI

### Context/problem

The project has multiple boundaries where errors could break behavior: HTTP validation, provider selection, chunking, vector persistence, retrieval, and citations. OpenAI calls should not be needed to test those behaviors.

### Decision

The repository uses pytest with focused tests for these components. HTTP tests use FastAPI's test client and isolated temporary SQLite databases. Fakes are used for provider behavior; the local-mode end-to-end test blocks importing OpenAI. GitHub Actions installs requirements, compiles the application and tests, and runs the full test suite on pushes and pull requests.

### Reasoning

Provider interfaces allow external calls to be replaced in tests. Temporary databases keep storage tests isolated. The CI workflow checks syntax and behavior in a repeatable Python 3.14 environment.

### Advantages

- Storage, provider, API, and full local workflow behaviors are tested separately.
- Most tests do not need paid API credentials or network calls to OpenAI.
- CI runs compile checks and the complete pytest suite for repository changes.

### Trade-offs

- Fakes verify the application's interaction with providers, not live provider quality or current account access.
- The repository does not include a production-scale retrieval evaluation dataset or quality benchmark.
- Passing tests cannot establish deployment security, operational capacity, or answer correctness for arbitrary corpora.

### Alternatives considered

The repository uses pytest and GitHub Actions. No alternative test framework or CI platform is recorded as formally evaluated.

## 11. API token authentication and document ownership

### Context/problem

The document API needs an identity boundary so one user cannot list, retrieve, or delete another user's documents. Public self-registration would not fit the project's administrator-provisioned local demo model.

### Decision

Administrators create users and API tokens with `python -m app.provisioning`. Tokens are generated with `secrets`, shown once in an interactive terminal, and stored only as SHA-256 hashes. FastAPI resolves bearer credentials to active users. Documents record a nullable `owner_id`; listing, retrieval, and deletion apply that owner in the service/store operations. Health and readiness remain public. Existing ownerless records stay unassigned and are excluded from user-scoped results.

### Reasoning

The design uses the existing SQLite and FastAPI dependency patterns without adding a public registration flow or an external identity service. Returning the same 404 for absent and non-owned document IDs avoids revealing whether another user's ID exists. Keeping legacy ownership null avoids assigning records to an arbitrary account.

### Advantages

- Plaintext API tokens are not written to SQLite and provisioning refuses redirected output.
- Token revocation and user deactivation take effect at authentication lookup.
- Database-level owner filters protect list, retrieval, and delete paths.
- Existing documents and vectors survive migration without fabricated ownership.

### Trade-offs

- Bearer tokens are secrets that clients must protect; the service has no browser login, token refresh, or administrator web interface.
- Legacy ownerless documents remain inaccessible through normal user endpoints until an administrator defines a safe assignment policy.
- The current rate limiter is process-local and does not coordinate across replicas.

### Alternatives considered

External identity providers and public registration are not implemented. They are general alternatives, not approaches formally evaluated by the repository.

## 12. Retrieval relevance, extractive abstention, and citations

### Context/problem

Cosine similarity returns relative rankings, but a top result may still be unrelated. Local feature-hash scores and hosted embedding scores need not share a useful cutoff. A returned citation list should also not imply that every retrieved passage was used in the answer.

### Decision

The existing `MIN_RELEVANCE_SCORE` remains the shared fallback. Optional `LOCAL_MIN_RELEVANCE_SCORE` and `OPENAI_MIN_RELEVANCE_SCORE` overrides allow separate tuning. `SQLiteVectorStore.search()` applies the minimum score to all owner- and document-scoped candidates before sorting and truncating to top-k. The local answer provider requires at least half of the question's meaningful terms to occur in a sentence. The RAG pipeline includes only source numbers referenced in the final answer; if references are absent or invalid, it returns the common no-information response with no sources. Both no-information paths use the same response text.

### Reasoning

The baseline smoke corpus demonstrated a false positive: the unrelated question “When is cafeteria access reviewed?” scored 0.3086 against the security passage, above the then-current 0.15 cutoff. Raising a shared cutoff based on this small local sample would be arbitrary and could reject relevant passages, especially for a different provider. Provider-specific overrides and a sentence-level evidence rule address different parts of the problem without claiming semantic understanding. Filtering before top-k lets lower-ranked above-threshold candidates remain eligible.

### Advantages

- Existing configuration remains the fallback, while providers can be calibrated separately.
- Low-scoring top results no longer consume top-k slots ahead of eligible passages.
- Local answers are copied from sentences with meaningful question-term coverage and retain source labels.
- The returned source metadata points only to labels cited by the answer.
- No additional dependency, model download, or API request is required for local evaluation.

### Trade-offs

- A small smoke dataset is not enough to establish production thresholds; operators should evaluate representative questions for their own corpus and embedding model.
- Term coverage can reject useful paraphrases and can still accept a coincidental match; it is not semantic verification.
- Valid source labels prove that a citation refers to supplied context, not that an LLM claim is entailed by that passage.
- The store still computes cosine scores for every eligible vector in Python.

### Alternatives considered

Increasing one global threshold was not selected because provider score distributions are not assumed equivalent and the observed local sample is too small to justify a universal cutoff. A trained reranker or semantic local model would add model/runtime complexity and is not implemented.

## 13. Current trade-offs, limitations, and future alternatives

### Context/problem

The project is an MVP that prioritizes a small, testable, locally runnable document-question-answering workflow. Its current architecture does not provide enterprise production controls or large-scale retrieval.

### Decision

The implemented system keeps the API, processing, providers, and SQLite store in one application. It supports text-based PDF and UTF-8 TXT files, local and OpenAI provider modes, bearer-token authentication, user-scoped document operations, and document-level CRUD. It does not implement OCR, a background job queue, a dedicated vector index, distributed rate limits, malware scanning, or a web-based administration interface.

### Reasoning

The current code favors straightforward service composition, file-based persistence, and injectable providers. These choices make the workflow testable and allow local use, while keeping scale and access-control limitations visible.

### Advantages

- The complete local path is usable without paid API access.
- Components have defined interfaces and focused tests.
- The app can use an OpenAI mode without replacing its ingestion and storage layers.

### Trade-offs

- The SQLite search scan and Python-side cosine calculation will become less suitable as the corpus grows.
- The API token model is intentionally small and requires administrators to provision users out of band.
- Per-user rate limits are local to one application process.
- OCR and non-PDF/TXT document formats are unsupported.
- Local retrieval is lexical, while OpenAI-generated answers can still be incorrect.

### Alternatives considered

The README and architecture guide identify PostgreSQL with pgvector, shared rate limiting, OCR, malware scanning, background ingestion, and evaluation/monitoring as possible future work. These are directions mentioned in project documentation, not implemented features or completed evaluations. Other scaling, identity, and document-processing products are general alternatives and have not been evaluated in this repository.

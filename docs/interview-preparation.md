# Project Interview Notes

Use these notes to explain the implementation accurately. Distinguish source-code behavior from historical verification results and avoid describing the demo as production deployment.

## Project overview

The project is a FastAPI application that ingests PDF and UTF-8 text documents, chunks and embeds their contents, stores chunks and vectors in SQLite, retrieves relevant passages, and returns answers with citations. The default workflow uses local deterministic feature-hash embeddings and extractive answering. Optional Ollama and OpenAI providers remain selectable.

## Architecture and design questions

### Why FastAPI?

Routes declare typed request/response models and dependencies, and FastAPI generates OpenAPI documentation. App construction supports injected settings and services for tests. Framework selection is an implementation decision; the repository does not contain a formal comparison study.

### Why SQLite and JSON vectors?

SQLite avoids a separate database service for this local MVP and provides transactions, constraints, and persistent storage. Vectors are JSON encoded and cosine similarity is calculated in Python. This is straightforward for a small corpus but scans the owner-eligible vectors linearly; it is not a large-scale vector index.

### How does local RAG work?

The local embedder hashes words and adjacent-word features into normalized vectors. The same embedder handles document chunks and queries. The store filters by user and optional document, computes cosine scores, applies the configured threshold, and returns top-k results. The extractive provider selects sentences that cover enough question terms. RAG validates source numbers before returning citations.

### What are the local mode limitations?

Feature hashing is lexical rather than semantic. It does not understand synonyms or paraphrases. Extractive answering copies selected evidence sentences and does not synthesize reasoning. The evaluation dataset has five cases, so its metrics are only a regression smoke check and do not represent broad real-world accuracy.

### How does the agent workflow work?

`ToolRegistry` exposes a small allowlist: knowledge search, document listing, and metadata-only document info. Pydantic schemas validate arguments, user IDs are passed to owner-filtered store calls, result sizes are capped, and unknown tools fail safely. `AgentOrchestrator` performs one search tool call and then delegates final answer/citation validation to the existing RAG pipeline. It is a bounded deterministic workflow, not model-directed autonomous tool calling.

### How are conversations protected?

Conversation and message tables have foreign keys. Storage queries combine conversation ID with the authenticated user ID. Message role/content and history sizes are bounded. Conversation deletion cascades to messages. Recent user questions can expand retrieval; assistant messages are not turned into tool instructions. There is no automatic retention scheduler or global memory.

### What prevents document-based prompt injection?

The Ollama/OpenAI grounding prompt labels document context as untrusted, but prompts alone are not a security boundary. The application restricts tool names, validates arguments, scopes all document reads by user, limits calls, and validates citations. Probabilistic model output still has residual risk and should be reviewed for consequential use.

## Operations and testing questions

### What is observed?

Middleware returns an opaque request ID and records method, route template, status, and duration. Structured logs and process-local `/metrics` do not include prompts, documents, answers, bearer tokens, or raw unknown paths. Metrics and rate limits reset on restart and are not shared across workers.

### What does the deployment setup provide?

The Dockerfile runs as a non-root user. Compose binds to localhost, persists `/data` in a named volume, uses a read-only root filesystem, drops Linux capabilities, and has a readiness health check. CI runs compilation and tests without API credentials or model downloads. Configuration review is not evidence that an image was built or deployed.

### How are tests kept independent of paid services?

Provider tests use fakes/mocks and deterministic local providers. The evaluation runner uses temporary SQLite storage and fictional data by default. Live Ollama inference is optional and not part of the normal test suite. Do not run OpenAI mode unless intentional paid use is approved.

## Honest trade-offs to mention

- SQLite cosine search scans the owner-filtered corpus and is not a vector database index.
- Duplicate suppression handles exact normalized duplicates, not semantic near-duplicates.
- The agent performs a second retrieval through RAG instead of passing tool results directly into answer construction.
- There is no dynamic model tool selection, business-system write action, queue, frontend, OCR, distributed rate limiting, or persistent metrics backend.
- Conversations persist until explicitly deleted; backups and database access need operational protection.
- Citations prove that a returned source label maps to a retrieved chunk, not that every generated claim is entailed by it.

## Beginner questions

### What problem does the project solve?

It gives an authenticated client a way to upload PDF/TXT material and ask questions that are answered from retrieved passages with source metadata. The system returns a no-information response if the local evidence selector cannot support an answer.

### What is RAG?

Retrieval-Augmented Generation first finds relevant source passages and then uses them as evidence for an answer. In this code, retrieval is SQLite cosine search; the default local answer path is extractive sentence selection rather than a generative LLM.

### Why does the project have a local mode?

The deterministic embedding and extractive providers let the complete ingestion/retrieval/answer path run without OpenAI credentials, fees, or a downloaded model. This is useful for reproducible local tests and demos, though its semantic capability is limited.

## Intermediate questions

### How does the service prevent one user from reading another user's documents?

Bearer tokens are hashed before database lookup. The authenticated user ID is passed into listing, retrieval, deletion, and metadata queries, and SQL applies the ownership filter. Document IDs alone do not authorize access.

### How are citations validated?

The RAG pipeline labels retrieved chunks and maps source numbers in the generated answer back to those exact retrieved chunks. Answers with missing or out-of-range source references abstain. This validates references, not semantic entailment.

### What does the new tool registry permit?

It permits only search over the current user's documents, listing the user's metadata, and metadata-only lookup for one owned document. Pydantic input models, bounded result sizes, and the fixed orchestrator constrain calls. It has no shell, arbitrary SQL, filesystem, or business-system write tool.

### How is follow-up context bounded?

Conversation IDs are owner-scoped. Messages are at most 12,000 characters, only the latest 200 are retained per conversation, and history reads are capped. At most two recent user questions are included in a retrieval query; assistant history is not used as tool instructions.

## Advanced system-design questions

### What would you change if the corpus grew substantially?

The current store loads the owner's eligible vectors and calculates cosine scores in Python, so computation grows linearly. I would first benchmark representative data and retrieval quality, then replace the store implementation behind the existing boundary with a suitable indexed backend such as PostgreSQL/pgvector. This is a future option, not a measured improvement in this repository.

### How would you make observability useful across multiple workers?

The current `/metrics` values are process-local. A multi-worker deployment would need shared aggregation or a metrics backend, plus deployment-level retention and access controls. The current design intentionally adds no external service requirement.

### What is the main residual agent security risk?

Probabilistic LLM answers can still be wrong or respond unsafely to adversarial content. Prompt instructions are defense-in-depth only. Authorization is enforced by application code, tool access is allowlisted, and citations are mapped back to owned retrieved chunks, but these controls do not prove semantic correctness.

### Why is the workflow deterministic rather than model-directed?

The existing extractive provider has no function-calling interface, and model-produced actions would need strict parsing and more failure modes. A one-search workflow is easy to test and exposes bounded behavior. A future local-model tool selector should be considered only with schema validation, iteration/call limits, adversarial tests, and measured value.

### What do the evaluation metrics mean here?

The runner reports retrieval metrics such as Precision@K, Recall@K, Hit Rate@K, and MRR, plus answer, abstention, citation, and expected-source checks. The current dataset has five fictional cases, so it is useful as a local regression set but too small to support broad quality claims or tune a production threshold.

# Project Resume Material

These are draft descriptions of implemented code, not claims about production users, traffic, business impact, or performance benchmarks.

- Built a FastAPI document-question-answering service with PDF/TXT ingestion, bounded extraction and chunking, SQLite persistence, user-scoped retrieval, and validated source citations.
- Implemented a no-cost local RAG path using deterministic feature-hash embeddings and extractive answers, while retaining optional Ollama and OpenAI provider adapters.
- Added bearer-token authentication, hashed token storage, per-user document ownership, SQLite schema migrations, and owner-filtered document access.
- Added a schema-validated allowlist of read-only agent tools and a bounded deterministic workflow that reuses the existing RAG answer and citation pipeline.
- Added user-owned conversation persistence, explicit deletion, bounded message/history sizes, and limited retrieval expansion from recent user questions.
- Added process-local request metrics and structured, content-safe operational logging, plus deterministic local RAG evaluation metrics.
- Containerized the service with a non-root runtime, loopback-only Compose port binding, a persistent named volume, and a lightweight GitHub Actions test workflow.

The repository's evaluation set currently contains five cases. Report its actual metric values only as evaluation results and label them with the provider, configuration, dataset size, and run date; do not present them as production accuracy or a benchmark.

# Local RAG Evaluation

## Purpose

HTTP success only shows that a request completed. This evaluation checks whether the existing RAG pipeline retrieves labeled evidence, returns expected facts, cites the expected sources, and abstains on unsupported questions. It is a small regression set for this repository, not a universal measure of RAG quality.

The evaluator lives under `evaluation/` and is invoked explicitly. It does not run during FastAPI startup or normal requests. It uses the production local feature-hash embedding implementation, `DocumentService`, `SQLiteVectorStore`, and `RAGPipeline`, with a temporary database and one temporary evaluation user. The database is deleted when the run ends. Production documents and the production database are not opened.

## Dataset

The fictional, version-controlled corpus is `evaluation/dataset.json`. It contains small made-up enterprise policies and five cases:

- Direct answerable questions with expected facts and supporting files.
- A multi-evidence question whose answer needs passages from two documents.
- A distractor question with related retrieved text that does not support the requested fact; the expected behavior is abstention.
- An unanswerable question with no matching evidence label.

The dataset is JSON with `schema_version: 1`, `documents`, and `cases`.

Each document has a unique `filename` and non-empty fictional `text`. Each case includes:

- `case_id`: stable identifier for the report.
- `question` and `category`: the test query and one of `answerable`, `multi_evidence`, `unanswerable`, or `distractor`.
- `answerable` and `expected_behavior`: consistent labels (`answer` or `abstain`).
- `expected_facts`: transparent phrases expected in a deterministic answer. Abstention cases have no facts.
- `retrieval_targets`: one or more `{filename, text_contains}` labels identifying evidence that retrieval should find. Distractor targets are related evidence, not proof that the question itself is answerable. An unanswerable case has no target.
- `expected_source_files`: files that a successful answer should cite; this is empty for abstention cases.

Dataset validation rejects duplicate IDs/filenames, missing text, evidence phrases absent from the named document, facts absent from expected source documents, inconsistent answerability labels, and invalid or incomplete multi-evidence/distractor labels. A retrieval target should be a short phrase that remains together in one configured chunk.

To add a case, add fictional content to `documents`, then add a unique case ID, category, question, supported expected facts, evidence phrases, and expected source filenames. Ensure each expected fact appears in a named expected source and each target phrase appears in its named document. Add at least two targets for `multi_evidence`; use a related but insufficient target for `distractor`. Run `python -m evaluation.run` and inspect individual case failures.

## Metrics

Retrieval metrics use the production embedding and SQLite cosine search, current `TOP_K`, and current local relevance threshold. The evaluator does not adjust defaults to improve its score.

- **Precision@K**: relevant retrieved chunks divided by K. If fewer than K results are returned, missing positions count as non-relevant.
- **Recall@K**: unique labeled evidence targets found in the top K divided by the number of expected targets.
- **Hit Rate@K**: 1 when at least one labeled target is found, otherwise 0.
- **MRR**: reciprocal rank of the first retrieved chunk matching a target; 1 for rank one, 1/2 for rank two, and 0 if none is found.

The summary reports the macro-average across cases with at least one retrieval target. Unsupported cases without evidence labels are marked not applicable for retrieval metrics; they are not counted as successful retrieval. Per-case output also shows no results, target hits, and retrieved filenames/ranks/scores so relevant misses and irrelevant results can be diagnosed.

Answer checks are simple and inspectable:

- **Answerable fact rate**: expected phrases found in returned answers divided by expected phrases.
- **Answerable case pass rate**: answerable cases containing all expected phrases with valid citations covering expected source files.
- **Correct abstention rate**: unanswerable and distractor cases returning the standard no-information answer with no citations.
- **Citation validity rate**: citations whose chunk IDs and document/filename metadata match chunks returned for that query.
- **Expected source coverage**: expected source files present among cited files.

These phrase checks do not prove semantic equivalence, factual entailment, or the absence of every unsupported statement. The evaluator does not claim to measure hallucinations perfectly. A deterministic sentence-copying provider can still miss paraphrases or select a misleading sentence; manual review remains useful.

## Running evaluations

From the repository directory in PowerShell:

```powershell
# Full deterministic run: retrieval plus extractive answer checks
python -m evaluation.run

# Run one part independently
python -m evaluation.run --mode retrieval
python -m evaluation.run --mode answers

# Select categories; repeat the option to include multiple categories
python -m evaluation.run --category answerable --category multi_evidence

# Save a JSON summary outside the repository
python -m evaluation.run --json-output "$env:TEMP\rag-evaluation.json"
```

The report contains the provider, mode, relevant local configuration, aggregate metrics, case statuses, failure codes, and retrieved filenames/ranks/scores. It omits questions, document text, generated answers, API credentials, and chunk contents. The JSON output path is opt-in.

## Provider behavior

The default `extractive` provider is local and deterministic. Embeddings, chunking, the production relevance threshold, top-k, retrieval, and citations use existing project components. OpenAI is not an available evaluator option and no OpenAI package call or credential is required.

Ollama can be selected explicitly:

```powershell
python -m evaluation.run --provider ollama
```

Ollama must already be running and the configured model must already be installed. The evaluation command never pulls or downloads a model. Selecting Ollama in `--mode retrieval` does not send an inference request; `all` and `answers` do send prompts to the explicitly configured local Ollama runtime. Local generated answers can vary by model/runtime settings, so their metrics are diagnostic rather than deterministic CI gates. The automated evaluation tests use no Ollama server or model.

## Limits and interpretation

The corpus is small, fictional, and hand-labeled. Its metrics are useful for regression and diagnosis, but they are not statistically representative of a production knowledge base. Feature-hash embeddings are lexical and can miss synonyms. Precision depends on the labeled top-k and threshold configuration. A phrase match does not establish semantic correctness, and valid source metadata does not prove that every answer claim follows from its cited passage. Review failures and expand the corpus with representative fictional cases before using results to compare major system changes.

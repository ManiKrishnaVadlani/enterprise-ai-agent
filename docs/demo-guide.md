# Local Demonstration Guide

This scenario uses fictional text and the deterministic local provider. It makes no OpenAI requests and does not download a model.

## 1. Start the local API

Install the dependencies from `requirements.txt`, set `AI_MODE=local` and `LLM_PROVIDER=extractive` (the defaults), then run:

```powershell
python -m app.provisioning create-user --display-name "Demo Alice" --label "demo"
$env:AGENT_API_TOKEN = "<paste the one-time token printed by the provisioning command>"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Treat the printed token as a password. It is only shown once; the database stores its SHA-256 hash. Do not paste a real token into this document or a Git-tracked file.

## 2. Prepare fictional policies

Create `access-policy.txt` containing:

```text
Remote access requires multifactor authentication. Access reviews happen quarterly.
```

Upload the raw file bytes. The API expects `X-Filename` and `application/octet-stream`, not multipart form data:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/documents/upload" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "X-Filename: access-policy.txt" `
  -H "Content-Type: application/octet-stream" `
  --data-binary "@access-policy.txt"
```

Save the returned document ID for deletion at the end.

## 3. Ask a supported question and inspect citations

```powershell
curl.exe -X POST "http://127.0.0.1:8000/ask" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"question":"When do access reviews happen?"}'
```

Expected behavior: the answer quotes the quarterly review sentence and includes a `sources` entry naming `access-policy.txt`. Relevance scores and IDs are generated for the current database and vary by upload.

## 4. Demonstrate safe abstention

Ask `What is the cafeteria menu?` using the same endpoint. With only the sample policy uploaded, the expected response is the no-information answer with an empty `sources` list.

## 5. Demonstrate tools and bounded orchestration

`GET /tools` lists the authenticated tools. `POST /agent` runs the fixed knowledge search and RAG answer workflow:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/agent" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"question":"What protects remote access?"}'
```

The response contains answer, citations, and a bounded workflow summary. This is deterministic orchestration; it is not an unconstrained autonomous agent.

## 6. Demonstrate conversation continuation

Create a conversation:

```powershell
$conversation = curl.exe -s -X POST "http://127.0.0.1:8000/conversations" `
  -H "Authorization: Bearer $env:AGENT_API_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"title":"Access policy demo"}' | ConvertFrom-Json
```

Send a follow-up with its `conversation_id` in the `/agent` request. The service stores the user question and assistant answer and includes up to two recent user questions in retrieval query expansion. It does not treat previous assistant text as a tool instruction.

## 7. Demonstrate user isolation

Provision a second user with `python -m app.provisioning create-user --display-name "Demo Bob" --label "demo"` and use Bob's token. Bob's `/documents` and `/conversations` results should not include Alice's records. Do not share Alice's token with Bob.

## 8. Run evaluation and inspect operations

Run `python -m evaluation.run` to execute the local fictional evaluation set. The API's authenticated `/metrics` endpoint reports in-process request counts and aggregate duration. `X-Request-ID` is returned on HTTP responses. Metrics reset at process restart.

## 9. Clean up

Delete the uploaded document using its returned ID and delete the conversation using its ID. Remove the temporary text file and clear the shell token with `Remove-Item Env:AGENT_API_TOKEN`. The project does not automatically expire conversations.

## Limitations

This demo uses lexical feature-hash embeddings and extractive answers. It demonstrates the real API flow, owner scoping, citations, abstention, tools, and conversation storage, but is not a semantic accuracy or production-scale benchmark. The five-case evaluation dataset is a smoke/regression set, not a broad quality study.

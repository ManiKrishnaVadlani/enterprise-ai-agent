# Enterprise AI Knowledge & Workflow Agent — Web Frontend

The frontend is a React + TypeScript single-page application for the existing FastAPI service. It uses the backend's current bearer-token authentication, raw-byte document upload, agent, and conversation APIs. It does not add backend endpoints or expose model/provider credentials.

## Prerequisites

- Node.js 22.12 or newer and npm.
- The existing FastAPI project and its Python dependencies. See the root README for Python setup.
- An API token provisioned by an administrator. The frontend does not provide public registration or token creation.

## Configure

Copy `.env.example` to `.env.local` if you need to change the default API URL:

```powershell
Copy-Item .env.example .env.local
```

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_MAX_UPLOAD_BYTES=10485760
```

The upload limit defaults to 10 MiB, matching the backend default. If `MAX_UPLOAD_BYTES` is customized in the backend environment, set `VITE_MAX_UPLOAD_BYTES` to the same byte count. Vite variables are public browser configuration; never put tokens or secrets in them.

The existing backend's default CORS configuration allows the Vite origin `http://127.0.0.1:3000`. Use that host and port for local use. If you change the frontend origin, configure the backend's `CORS_ORIGINS` accordingly.

## Start the backend

From the repository root, activate the existing Python environment and start FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`; its readiness endpoint is `http://127.0.0.1:8000/ready`. The project's local mode works without OpenAI credentials or paid API calls. Local Ollama may be configured by the backend separately.

Provision a user and token from an administrator-controlled terminal:

```powershell
python -m app.provisioning create-user --display-name "Local user" --label "frontend demo"
```

The backend prints the plaintext token once. Copy it securely for the sign-in step. SQLite stores only its hash. Do not put the token in this file, an environment variable prefixed with `VITE_`, or a URL.

## Install and run the frontend

From `frontend/`:

```powershell
npm install
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000), then sign in with the administrator-issued API token. The token is held in browser `sessionStorage`, sent in the `Authorization: Bearer` header, and cleared on logout or an HTTP 401 response.

## Build

```powershell
npm run typecheck
npm run build
npm run preview
```

The production bundle is generated in `frontend/dist/`. The preview server uses port 3000; ensure the API CORS allowlist includes the origin from which it is served.

## Using the application

- **Overview:** displays document and chunk totals from `GET /documents`, conversation count from `GET /conversations`, and readiness from `GET /ready`.
- **Knowledge base:** uploads PDF/TXT file bytes to `POST /documents/upload` with `X-Filename` and `Content-Type: application/octet-stream`, lists documents from `GET /documents`, and deletes through `DELETE /documents/{document_id}`. Upload progress and validation are shown in the page.
- **AI assistant:** creates a saved conversation with `POST /conversations`, runs grounded answers through `POST /agent`, loads saved history, and displays only citation metadata returned with the live answer.
- **Conversations:** lists, resumes, and deletes the current user's conversations through the existing API.
- **Settings:** displays the API URL and public health/readiness status; the API does not expose AI provider configuration.

## Known limitations

- Authentication uses the backend's pre-provisioned bearer tokens; there is no username/password flow, user administration, or token issuance UI.
- The token is stored in `sessionStorage`: this avoids persistence across browser sessions but remains accessible to JavaScript in the current page. Use only with a trusted, same-origin frontend and protect against cross-site scripting.
- The UI applies the configured client-side upload size limit; the backend remains authoritative. Keep both limits aligned.
- Saved conversation messages contain text only. The backend does not persist citation objects, so citations are shown for newly returned answers and cannot be reconstructed for old messages.
- Provider/model details are not exposed by the backend and are intentionally not guessed by the UI.
- This is a local development frontend. Production hosting, TLS, CSP, deployment hardening, and browser end-to-end testing require separate environment-specific work.

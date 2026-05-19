# Docker Deployment Fixes

Issues encountered and fixed when running `docker-compose up --build` for the first time.

---

## 1. Missing `.env` file

**Error:** `env file .env not found`

**Cause:** `docker-compose.yml` references `.env` for the backend service but the file did not exist.

**Fix:** Copy `.env.example` to `.env` and fill in your API key:

```bash
cp .env.example .env
```

Set `LLM_PROVIDER` to either `anthropic` or `openai` and supply the corresponding key:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

---

## 2. Frontend build fails — wrong entry point in `index.html`

**Error:** `Rollup failed to resolve import "/src/main.tsx" from "/app/index.html"`

**Cause:** `index.html` referenced `main.tsx` but the actual file is `main.js`.

**Fix:** `frontend/index.html` line 14:

```diff
- <script type="module" src="/src/main.tsx"></script>
+ <script type="module" src="/src/main.js"></script>
```

---

## 3. Frontend build fails — TypeScript compiler runs on plain JS source

**Error:** `tsc` exits with errors because source files are `.js`, not `.ts`/`.tsx`.

**Cause:** `package.json` build script ran `tsc && vite build`. Since all source files are plain JavaScript, `tsc` fails.

**Fix:** `frontend/package.json`:

```diff
- "build": "tsc && vite build",
+ "build": "vite build",
```

---

## 4. Backend container crashes — wrong uvicorn module path

**Error:** `ModuleNotFoundError: No module named 'backend'`

**Cause:** The original `backend/Dockerfile` used `WORKDIR /app` and copied files directly into `/app`, but the uvicorn command was `backend.main:app`. Python looked for a `backend` package inside `/app`, which didn't exist — the files were at `/app/main.py`, `/app/auth.py`, etc.

The source code itself also uses `from backend.xxx import ...` style imports throughout (`main.py`, `auth.py`, `agent.py`), so the package must be importable as `backend`.

**Fix:** `backend/Dockerfile` — copy files into `/backend/` and set `PYTHONPATH=/` so Python can resolve the `backend` package:

```dockerfile
FROM python:3.11-slim
WORKDIR /
COPY requirements.txt /backend/requirements.txt
RUN pip install --no-cache-dir -r /backend/requirements.txt
COPY . /backend/
ENV PYTHONPATH=/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## 5. CRM-MCP container crashes — same package path issue

**Error:** `ModuleNotFoundError: No module named 'crm_mcp'`

**Cause:** Same root cause as #4. `server.py` imports `from crm_mcp.db import get_db` but files were copied flat into `/app`.

**Fix:** `crm_mcp/Dockerfile` — copy files into `/crm_mcp/` and set `PYTHONPATH=/`:

```dockerfile
FROM python:3.11-slim
WORKDIR /
COPY requirements.txt /crm_mcp/requirements.txt
RUN pip install --no-cache-dir -r /crm_mcp/requirements.txt
COPY . /crm_mcp/
ENV PYTHONPATH=/
CMD ["python", "/crm_mcp/server.py"]
```

---

## 6. Frontend shows blank dark page — macOS node_modules copied into Docker

**Symptom:** `docker compose up --build` completes, but opening http://localhost:5173 shows only a dark background with no React content.

**Cause:** No `frontend/.dockerignore` existed. The Dockerfile runs `npm install` (installing Alpine Linux binaries), then `COPY . .` overwrites `node_modules` with the macOS-specific ones from the host. Vite's native `esbuild` binary is platform-specific — the macOS binary doesn't run on Alpine Linux, so the production build produces output with no JS bundle.

**Fix:** Add `frontend/.dockerignore`:

```
node_modules
dist
```

This prevents the host `node_modules` from entering the Docker build context, preserving the Linux binaries installed by `RUN npm install`.

---

## Summary of all file changes

| File | Change |
|------|--------|
| `.env` | Created from `.env.example` with `LLM_PROVIDER` and API key set |
| `frontend/index.html` | `main.tsx` → `main.js` |
| `frontend/package.json` | Build script: removed `tsc &&` prefix |
| `backend/Dockerfile` | `WORKDIR /`, copy to `/backend/`, `ENV PYTHONPATH=/` |
| `crm_mcp/Dockerfile` | `WORKDIR /`, copy to `/crm_mcp/`, `ENV PYTHONPATH=/` |
| `frontend/.dockerignore` | Exclude `node_modules` and `dist` from Docker build context |
| `backend/.dockerignore` | Exclude `__pycache__`, `.venv`, etc. |
| `crm_mcp/.dockerignore` | Exclude `__pycache__`, `.venv`, `crm.db` |

---

## Root cause summary for developers

The backend and crm-mcp packages use **absolute package-style imports** (`from backend.xxx` / `from crm_mcp.xxx`) throughout the source code. For these imports to work, the parent directory of each package must be on `sys.path`. The Dockerfiles were originally copying source files flat into the working directory (`/app`), which only puts the *contents* of the package on the path — not the package itself.

The fix is to copy each service's source into a subdirectory matching its package name and expose the parent via `PYTHONPATH`.

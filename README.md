# ReviewLens — LLM-powered Code Review Assistant

Code review grounded in repository context. Paste a unified diff or import a GitHub pull request, retrieve related code and conventions, and inspect actionable findings alongside the changed lines.

**Python · FastAPI · React · TypeScript · OpenAI · PostgreSQL / pgvector**

## What it does

- Imports GitHub PR diffs without posting comments or modifying repositories.
- Indexes selected source files with overlapping, line-addressable chunks.
- Retrieves relevant context using embeddings and cosine similarity.
- Uses GPT-4 (configurable) to produce structured review findings.
- Validates finding locations against added lines and citations against retrieved chunks.
- Displays the diff, severity, explanation, suggested fix, and supporting context.
- Saves review history and helpful/not-helpful feedback.
- Runs a clearly labeled, deterministic demo without an API key.

This is a working prototype, not a claim of production adoption. There are no measured claims of 50 PRs/week, 85% helpfulness, or 60% fewer generic suggestions. Feedback percentages in the interface are calculated only from actual votes on that review. Embeddings are generated with a pretrained model, **not custom-trained**.

## Quick start: local demo

Requirements: Python 3.12+ and Node.js 22+.

From the repository root:

```sh
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```sh
source .venv/bin/activate
```

Install and build:

```sh
pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The default configuration uses SQLite and demo mode; no `.env` file is required.

1. Click **Load example**.
2. Open **Codebase**, then **Index 2 files**.
3. Return to **Review changes**, then **Run review**.
4. Inspect the two heuristic findings and retrieved snippets.
5. Rate a finding, then reopen it from **Review history** to see persisted feedback.

Demo mode detects only a small set of suspicious Python patterns. Its local hashed vectors demonstrate retrieval plumbing, not semantic embedding quality. Demo findings intentionally do not fabricate citations to retrieved context.

## Enable LLM reviews

Copy `.env.example` to `.env` and set these values locally:

```dotenv
REVIEW_PROVIDER=openai
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4
EMBEDDING_MODEL=text-embedding-3-small
```

Restart the server and **reindex source files** after changing provider or embedding model. Retrieval filters by embedding model/version, so incompatible vectors are never mixed.

The server sends selected source chunks to OpenAI for embeddings and sends the diff plus retrieved context for review. Only index code you are authorized to send. Keys remain on the server; `.env` is ignored by Git. API usage is billed to your account. Model access depends on your OpenAI account. The default preserves the original GPT-4 project specification; another Chat Completions-compatible model can be configured, but models with different parameter requirements may need an adapter change.

Live OpenAI requests require your key. Automated tests use stubbed provider responses, not a paid live model. A failed model call returns an error; it never silently substitutes demo output.

API documentation: [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [Embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create)

## PostgreSQL and pgvector

With Docker installed:

```sh
docker compose up --build
```

The app is available at **http://127.0.0.1:8000**. Compose starts PostgreSQL 16 with pgvector and a persistent named volume. The app creates the extension and tables at startup. The compose password is for this isolated local database, not a production credential. The database is not exposed on a host port.

Alternatively set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB`. The database role needs permission to create the vector extension (or have an administrator provision it first).

PostgreSQL performs exact cosine ranking in SQL using pgvector. SQLite stores vectors as JSON and ranks them in Python for a small local workspace. There is no ANN index or large-repository scaling claim.

## Development

Run the Python server as above. In a second terminal:

```sh
npm --prefix frontend run dev
```

Vite serves the interface at http://127.0.0.1:5173 and proxies `/api` to port 8000. API documentation is at http://127.0.0.1:8000/docs.

```sh
python -m pytest backend/tests -q
npm --prefix frontend run build
```

An optional CI template is provided at `docs/github-actions-ci.yml.example`. To enable it, copy it to `.github/workflows/ci.yml` and push using credentials with workflow permissions. It runs the backend suite and the TypeScript/production build. Tests cover review persistence, feedback, reindexing, project isolation, malformed diffs, unsafe file paths, invalid model citations/locations, provider failures, origin checks, request size limits, and the OpenAI adapter.

## Architecture

```text
Source files → overlapping chunks → embeddings → vector storage
                                                    ↓
Unified diff → added-line query → retrieve context → model review
                                                    ↓
                         validate locations/citations → saved review
                                                    ↓
                                    React diff + findings + feedback
```

- `backend/main.py`: HTTP API, review orchestration, GitHub import, local origin guard.
- `backend/providers.py`: OpenAI adapter, prompt, explicit demo implementation.
- `backend/store.py`: SQLAlchemy persistence, chunking, PostgreSQL/SQLite retrieval.
- `backend/diff.py`: unified diff parsing and new-side line mapping.
- `frontend/src/main.tsx`: review, codebase, and history interfaces.

## Scope and limitations

- Local, single-user tool. It has no authentication, tenant isolation, job queue, or production rate limiting. Do not expose it publicly without adding them.
- Source indexing is explicit: select related source files, tests, and conventions. Importing a PR imports its diff only; it does not index the entire repository or fetch base-commit context automatically.
- Reviews accept text diffs with added lines; binary changes, deletion-only diffs, and complicated quoted Git paths are outside this MVP.
- Limits: 40 source files per index request, 50,000 characters per file, 400 chunks per indexing batch, 50,000 diff characters and 500 diff lines. Model requests also have a conservative character budget and may still exceed a model's token limit on unusually dense inputs.
- GPT-4 output is schema-validated JSON. Invalid or incomplete output produces an error. Location/citation validation confirms references exist, not that the model's reasoning is correct.
- No code execution, automatic patches, GitHub comments, or test-verification claims. Humans inspect suggestions and run tests.
- Uploaded code and review history are stored unencrypted in the configured local database. Hidden files and common key-file extensions are blocked; this is not comprehensive secret scanning.
- PostgreSQL/Docker and live model calls require their respective services; a SQLite/demo test pass does not verify those deployments.

## Evaluate it honestly

Start with a labeled collection of small, historical bug-introducing diffs and their relevant context. Compare the same model with and without retrieval, blinded to the evaluator. Record true defects, unsupported suggestions, missed defects, and human helpfulness votes. Report sample sizes and define denominators. The included sample is a smoke test, not a quality benchmark.

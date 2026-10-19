import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .diff import parse_diff
from .providers import Provider, ProviderError
from .sample import SAMPLE
from .schemas import FeedbackRequest, IndexRequest, PullRequestImport, ReviewRequest
from .store import Store, chunk_file


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings.database_url)
    provider = Provider(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.engine.dispose()

    app = FastAPI(title='ReviewLens API', version='1.0.0', lifespan=lifespan)
    app.state.store = store
    app.state.provider = provider

    @app.middleware('http')
    async def local_api_guard(request: Request, call_next):
        # Local development tool: reject cross-origin browser writes and oversized requests.
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': 'Cross-origin writes are not allowed.'}, status_code=403)
            size = 0
            pieces = []
            async for piece in request.stream():
                size += len(piece)
                if size > 2200000:
                    return JSONResponse({'detail': 'Request exceeds 2.2 MB.'}, status_code=413)
                pieces.append(piece)
            request._body = b''.join(pieces)
        return await call_next(request)

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=502)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'provider': settings.provider,
                'model': settings.model if settings.provider == 'openai' else 'deterministic heuristics',
                'embedding': settings.embedding_id, 'database': store.engine.dialect.name}

    @app.get('/api/sample')
    def sample():
        return SAMPLE

    @app.get('/api/projects/{project:path}/index')
    def inventory(project: str):
        return store.inventory(project)

    @app.post('/api/index')
    def index(payload: IndexRequest):
        paths = [f.path for f in payload.files]
        if len(set(paths)) != len(paths):
            raise HTTPException(422, 'Each uploaded file needs a unique path.')
        chunks = [c for f in payload.files for c in chunk_file(f.path, f.content)]
        if len(chunks) > 400:
            raise HTTPException(422, 'Index at most 400 chunks per request. Use smaller files.')
        if not chunks or any(len(c['content']) > 16000 for c in chunks):
            raise HTTPException(422, 'Files must contain text and chunks must be below 16,000 characters.')
        vectors = provider.embed([c['path'] + '\n' + c['content'] for c in chunks])
        store.index(payload.project, paths, chunks, vectors, settings.embedding_id)
        return {**store.inventory(payload.project), 'embedding': settings.embedding_id}

    @app.post('/api/reviews')
    def review(payload: ReviewRequest):
        try:
            files = parse_diff(payload.diff)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if sum(len(f['lines']) for f in files) > 500:
            raise HTTPException(422, 'Review at most 500 diff lines at a time.')
        query = '\n'.join(f['path'] + '\n' + '\n'.join(l['text'] for l in f['lines'] if l['kind'] == '+') for f in files)
        vector = provider.embed([query])[0]
        context = store.retrieve(payload.project, vector, settings.embedding_id)
        result = provider.review(files, context)
        valid_locations = {(f['path'], line) for f in files for line in f['added_lines']}
        context_ids = {c['id'] for c in context}
        findings = []
        dropped = 0
        for finding in result.findings:
            if (finding.path, finding.line) not in valid_locations or not set(finding.context_ids) <= context_ids:
                dropped += 1
                continue
            findings.append({**finding.model_dump(), 'helpful': None})
        warnings = []
        if not context:
            warnings.append('No matching indexed context. Upload relevant source files to ground this review.')
        if dropped:
            warnings.append(f'{dropped} finding(s) omitted because locations or citations could not be validated.')
        return store.save_review(payload.project, {'title': payload.title, 'summary': result.summary,
            'findings': findings, 'files': files, 'context': context, 'warnings': warnings,
            'provider': settings.provider, 'model': settings.model if settings.provider == 'openai' else 'demo-rules-v1'})

    @app.get('/api/reviews')
    def history(project: str):
        return store.list_reviews(project)

    @app.get('/api/reviews/{review_id}')
    def get_review(review_id: str):
        result = store.get_review(review_id)
        if result is None:
            raise HTTPException(404, 'Review not found.')
        return result

    @app.post('/api/reviews/{review_id}/findings/{finding_index}/feedback')
    def feedback(review_id: str, finding_index: int, payload: FeedbackRequest):
        result = store.feedback(review_id, finding_index, payload.helpful)
        if result is None:
            raise HTTPException(404, 'Finding not found.')
        return result

    @app.post('/api/github/import')
    def github_import(payload: PullRequestImport):
        match = re.fullmatch(r'https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)/?', payload.url.strip())
        if not match:
            raise HTTPException(422, 'Use a github.com OWNER/REPO/pull/NUMBER URL.')
        owner, repo, number = match.groups()
        headers = {'Accept': 'application/vnd.github.diff', 'X-GitHub-Api-Version': '2022-11-28'}
        if settings.github_token:
            headers['Authorization'] = 'Bearer ' + settings.github_token
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                with client.stream('GET', f'https://api.github.com/repos/{owner}/{repo}/pulls/{number}', headers=headers) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for piece in response.iter_bytes():
                        body.extend(piece)
                        if len(body) > 100000:
                            raise HTTPException(422, 'This pull request is too large. Paste a smaller diff.')
                diff = body.decode('utf-8')
            if len(diff) > 50000:
                raise HTTPException(422, 'This pull request is too large. Paste a smaller diff.')
            parse_diff(diff)
            return {'project': f'{owner}/{repo}', 'title': f'{owner}/{repo} #{number}', 'diff': diff}
        except (httpx.HTTPError, UnicodeError, ValueError):
            raise HTTPException(502, 'Could not import the PR. Check its URL, GitHub rate limits, or the server token. A text diff with added lines is required.') from None

    frontend = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
    if frontend.exists():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    return app

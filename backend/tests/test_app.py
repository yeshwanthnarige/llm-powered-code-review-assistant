import json

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.diff import parse_diff
from backend.main import create_app
from backend.providers import Provider, ProviderError
from backend.sample import SAMPLE
from backend.schemas import ModelReview


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "test.db"}', provider='demo'))
    with TestClient(app) as client:
        yield client


def run_sample(client):
    response = client.post('/api/reviews', json={k: SAMPLE[k] for k in ['project', 'title', 'diff']})
    assert response.status_code == 200, response.text
    return response.json()


def test_complete_review_and_feedback_persist(client):
    indexed = client.post('/api/index', json={'project': SAMPLE['project'], 'files': SAMPLE['files']})
    assert indexed.status_code == 200
    assert len(indexed.json()['files']) == 2
    review = run_sample(client)
    assert review['provider'] == 'demo'
    assert len(review['findings']) == 2
    assert len(review['context']) == 2
    assert review['findings'][0]['line'] == 3
    assert review['findings'][0]['context_ids'] == []  # Demo must not fabricate grounding.
    response = client.post(f'/api/reviews/{review["id"]}/findings/0/feedback', json={'helpful': True})
    assert response.status_code == 200
    assert client.get('/api/reviews/' + review['id']).json()['findings'][0]['helpful'] is True
    assert len(client.get('/api/reviews', params={'project': SAMPLE['project']}).json()) == 1


def test_reindex_replaces_old_chunks_and_isolates_projects(client):
    payload = {'project': 'one', 'files': [{'path': 'rules.md', 'content': 'old rule\n' * 100}]}
    assert client.post('/api/index', json=payload).status_code == 200
    payload['files'][0]['content'] = 'new rule'
    assert client.post('/api/index', json=payload).json()['chunks'] == 1
    assert client.get('/api/projects/two/index').json()['chunks'] == 0
    assert not client.app.state.store.retrieve('one', [0.0] * 256, 'different-model')


@pytest.mark.parametrize('path', ['../secret.py', '/etc/passwd', '.env', 'config/key.pem', 'C:/secret.txt'])
def test_unsafe_context_paths_rejected(client, path):
    response = client.post('/api/index', json={'project': 'one', 'files': [{'path': path, 'content': 'x'}]})
    assert response.status_code == 422


@pytest.mark.parametrize('diff', ['not a diff', SAMPLE['diff'].replace('+1,7', '+1,99'), '--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n'])
def test_invalid_or_truncated_diffs_rejected(client, diff):
    assert client.post('/api/reviews', json={'project': 'one', 'diff': diff}).status_code == 422


def test_multiple_hunks_and_deleted_lines():
    diff = '--- a/a.py\n+++ b/a.py\n@@ -2,2 +2,2 @@\n-old\n+new\n same\n@@ -10 +10 @@\n-a\n+b\n'
    files = parse_diff(diff)
    assert files[0]['added_lines'] == [2, 10]
    assert files[0]['lines'][0]['number'] is None


def test_hallucinated_locations_and_citations_are_filtered(client, monkeypatch):
    base = {'path': 'checkout/api.py', 'line': 3, 'severity': 'high', 'title': 'Issue', 'explanation': 'Evidence', 'suggestion': 'Fix it', 'context_ids': []}
    monkeypatch.setattr(client.app.state.provider, 'review', lambda *args: ModelReview(summary='Review', findings=[
        base, {**base, 'line': 999}, {**base, 'context_ids': ['invented-citation']}]))
    review = run_sample(client)
    assert len(review['findings']) == 1
    assert any('2 finding(s)' in warning for warning in review['warnings'])


def test_provider_failure_does_not_save_or_fallback(client, monkeypatch):
    def fail(*args):
        raise ProviderError('Model unavailable')
    monkeypatch.setattr(client.app.state.provider, 'review', fail)
    response = client.post('/api/reviews', json={k: SAMPLE[k] for k in ['project', 'title', 'diff']})
    assert response.status_code == 502
    assert client.get('/api/reviews', params={'project': SAMPLE['project']}).json() == []


def test_no_context_and_no_findings_are_honest(client):
    response = client.post('/api/reviews', json={'project': 'empty', 'diff': '--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n'})
    assert response.status_code == 200
    assert response.json()['findings'] == []
    assert response.json()['warnings']


def test_cross_origin_and_oversized_requests_rejected(client):
    assert client.post('/api/index', headers={'Origin': 'https://untrusted.example'}, json={}).status_code == 403
    assert client.post('/api/index', content='x' * 2200001).status_code == 413


def test_duplicate_source_paths_rejected(client):
    file = {'path': 'a.py', 'content': 'x = 1'}
    assert client.post('/api/index', json={'project': 'x', 'files': [file, file]}).status_code == 422


@pytest.mark.parametrize('url', ['http://localhost:1234', 'https://github.com.evil.test/u/r/pull/1', 'https://github.com/u/r/pull/1?x=y'])
def test_github_import_only_accepts_exact_pr_urls(client, url):
    assert client.post('/api/github/import', json={'url': url}).status_code == 422


def test_openai_adapter_validates_output_and_embedding_order(monkeypatch):
    provider = Provider(Settings(provider='openai', api_key='test-placeholder'))
    def fake_request(endpoint, payload):
        if endpoint == 'embeddings':
            assert payload['dimensions'] == 256
            return {'data': [{'index': 1, 'embedding': [1.0] * 256}, {'index': 0, 'embedding': [0.0] * 256}]}
        assert payload['model'] == 'gpt-4'
        assert 'untrusted' in payload['messages'][0]['content']
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'summary': 'No concrete defect found.', 'findings': []})}}]}
    monkeypatch.setattr(provider, '_request', fake_request)
    assert provider.embed(['a', 'b'])[0] == [0.0] * 256
    assert provider.review(parse_diff(SAMPLE['diff']), []).findings == []
    monkeypatch.setattr(provider, '_request', lambda *args: {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})
    with pytest.raises(ProviderError):
        provider.review(parse_diff(SAMPLE['diff']), [])


def test_unknown_review_and_feedback(client):
    assert client.get('/api/reviews/missing').status_code == 404
    assert client.post('/api/reviews/missing/findings/0/feedback', json={'helpful': True}).status_code == 404

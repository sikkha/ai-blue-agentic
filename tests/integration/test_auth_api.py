from threading import Event

import pytest
from fastapi.testclient import TestClient

from backend.accounts import Accounts
from backend.web import COOKIE, Workspaces, create_app

ORIGIN = 'https://public.geopolitics.io'
PASSWORD = 'a synthetic test password only'


@pytest.fixture
def deployment(tmp_path):
    root = tmp_path / 'auth'
    app = create_app('config/workflow.yaml', directory=root, origin=ORIGIN)
    store = Accounts(root)
    store.bootstrap_admin('operator', PASSWORD)
    return app, store


def sign_in(client, username, password=PASSWORD):
    return client.post('/api/auth/login', json={'username': username, 'password': password},
                       headers={'Origin': ORIGIN})


def signed_headers(response):
    return {'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf']}


def test_every_protected_route_family_rejects_direct_requests(deployment):
    app, _ = deployment
    with TestClient(app, base_url=ORIGIN) as client:
        paths = [('GET', route) for route in (
            '/api/auth/session', '/api/auth/users', '/api/workspace/tree', '/api/workspace/file',
            '/api/sessions', '/api/sessions/abc/trace', '/api/sessions/abc/transcript', '/api/meters', '/api/settings',
        )] + [('POST', route) for route in (
            '/api/auth/logout', '/api/auth/users', '/api/workspace/create', '/api/workspace/move',
            '/api/workspace/delete', '/api/workspace/graph/build', '/api/chat', '/api/uploads',
            '/api/approvals/abc', '/api/turns/abc/stop',
        )] + [('PUT', '/api/settings'), ('PUT', '/api/workspace/file'), ('PATCH', '/api/auth/users/1')]
        for method, path in paths:
            assert client.request(method, path, json={}).status_code == 401, (method, path)
        assert client.get('/docs').status_code == 404
        assert client.post('/api/auth/register', json={}).status_code == 401


def test_login_cookie_csrf_logout_and_reuse(deployment):
    app, _ = deployment
    with TestClient(app, base_url=ORIGIN) as client:
        payload = {'username': 'operator', 'password': PASSWORD}
        assert client.post('/api/auth/login', json=payload).status_code == 403
        login = sign_in(client, 'operator')
        assert login.status_code == 200
        attrs = login.headers['set-cookie'].lower()
        assert all(attr in attrs for attr in ('secure', 'httponly', 'samesite=strict', 'path=/'))
        assert 'domain=' not in attrs
        assert client.get('/api/auth/session').headers['cache-control'] == 'no-store'
        token = client.cookies.get(COOKIE)
        headers = signed_headers(login)
        assert client.post('/api/auth/logout', headers={'Origin': ORIGIN}).status_code == 403
        assert client.post('/api/auth/logout', headers={**headers, 'Origin': 'https://untrusted.test'}).status_code == 403
        assert client.post('/api/auth/logout', headers=headers).status_code == 204
        assert client.get('/api/auth/session', headers={'Cookie': f'{COOKIE}={token}'}).status_code == 401


def test_wrong_credentials_and_rate_limit_survive_new_client(deployment):
    app, _ = deployment
    with TestClient(app, base_url=ORIGIN) as client:
        unknown = sign_in(client, 'unknown', 'invalid').json()
        for _ in range(5):
            outcome = sign_in(client, 'operator', 'invalid')
            assert outcome.status_code == 401 and outcome.json() == unknown
        client.cookies.clear()
        assert sign_in(client, 'operator').status_code == 429


def test_roles_feature_assignment_reset_and_disable(deployment):
    app, _ = deployment
    with TestClient(app, base_url=ORIGIN) as admin, TestClient(app, base_url=ORIGIN) as member:
        admin_headers = signed_headers(sign_in(admin, 'operator'))
        created = admin.post('/api/auth/users', headers=admin_headers, json={'username': 'member', 'password': PASSWORD})
        assert created.status_code == 201 and 'password' not in created.text
        user_id = created.json()['id']
        login = sign_in(member, 'member')
        member_headers = signed_headers(login)
        assert member.get('/api/workspace/tree').status_code == 200
        assert member.get('/api/auth/users').status_code == 403
        assert member.get('/api/settings').status_code == 403
        assert member.put('/api/settings', headers=member_headers, json={}).status_code == 403
        for route in ('/api/approvals/something', '/api/chat', '/api/uploads', '/api/workspace/graph/build'):
            assert member.post(route, headers=member_headers, json={}).status_code == 403
        assert admin.patch(f'/api/auth/users/{user_id}', headers=admin_headers, json={'agent_enabled': True}).status_code == 200
        assert member.get('/api/auth/session').status_code == 401
        assert sign_in(member, 'member').json()['user']['agent_enabled']
        replacement = 'a replacement synthetic test password'
        assert admin.patch(f'/api/auth/users/{user_id}', headers=admin_headers, json={'password': replacement, 'role': 'ADMIN'}).status_code == 200
        assert member.get('/api/auth/session').status_code == 401
        assert sign_in(member, 'member').status_code == 401
        assert sign_in(member, 'member', replacement).json()['user']['role'] == 'ADMIN'
        assert admin.patch(f'/api/auth/users/{user_id}', headers=admin_headers, json={'enabled': False}).status_code == 200
        assert member.get('/api/auth/session').status_code == 401
        assert admin.patch('/api/auth/users/1', headers=admin_headers, json={'role': 'USER'}).status_code == 409
        assert admin.put('/api/settings', headers=admin_headers, json={'tools': ['bash']}).status_code == 422


def test_data_and_approval_ids_are_per_account(deployment, monkeypatch):
    app, store = deployment
    token, _ = store.login('operator', PASSWORD, 'setup')
    first = store.create('first', PASSWORD, 'USER', agent_enabled=True, admin_token=token)
    store.create('second', PASSWORD, 'USER', agent_enabled=True, admin_token=token)
    original = Workspaces.build
    built = {}

    def capture(self, user_id):
        built[user_id] = original(self, user_id)
        return built[user_id]

    monkeypatch.setattr(Workspaces, 'build', capture)
    with TestClient(app, base_url=ORIGIN) as a, TestClient(app, base_url=ORIGIN) as b:
        a_headers = signed_headers(sign_in(a, 'first'))
        b_headers = signed_headers(sign_in(b, 'second'))
        assert a.post('/api/workspace/create', headers=a_headers, json={'path': 'private.md', 'kind': 'file'}).status_code == 200
        assert b.get('/api/workspace/file', params={'path': 'private.md'}).status_code == 404
        uploaded = a.post('/api/uploads', headers=a_headers, files={'file': ('private.txt', b'synthetic')})
        assert uploaded.status_code == 200
        assert b.post('/api/chat', headers=b_headers, json={'files': [uploaded.json()['id']]}).status_code == 404
        gate = {'event': Event(), 'answer': ('deny', '')}
        built[first['id']].state.approvals['test-id'] = gate
        route = '/api/approvals/test-id'
        assert b.post(route, headers=b_headers, json={'decision': 'allow'}).status_code == 404
        assert not gate['event'].is_set()
        assert a.post(route, headers=a_headers, json={'decision': 'allow'}).status_code == 200
        assert gate['event'].is_set()


def test_expired_cookie_and_previous_browser_session_cannot_read(deployment):
    app, store = deployment
    token, _ = store.login('operator', PASSWORD, 'setup')
    store.create('member', PASSWORD, 'USER', admin_token=token)
    with TestClient(app, base_url=ORIGIN) as client:
        previous = sign_in(client, 'operator').json()['csrf']
        assert sign_in(client, 'member').status_code == 200
        assert client.get('/api/workspace/tree', headers={'X-CSRF-Token': previous}).status_code == 401
        assert client.get('/api/workspace/tree').status_code == 200
        with store.connect() as db:
            db.execute('UPDATE auth_sessions SET expires_at=0')
        assert client.get('/api/auth/session').status_code == 401
        assert client.get('/api/workspace/tree').status_code == 401

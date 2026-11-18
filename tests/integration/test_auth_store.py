import sqlite3
import time

import pytest

from backend.accounts import ATTEMPT_WINDOW, Accounts, RateLimited, digest

PASSWORD = 'long test password, not a deployment credential'


def test_migration_bootstrap_and_password_storage(tmp_path):
    directory = tmp_path / 'auth'
    accounts = Accounts(directory)
    user = accounts.bootstrap_admin('First.Admin', PASSWORD)
    assert user['username'] == 'first.admin'
    assert not user['agent_enabled']
    with accounts.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        stored = db.execute('SELECT password_hash FROM users').fetchone()[0]
        assert stored.startswith('$argon2id$') and PASSWORD not in stored
    assert Accounts(directory).users() == [user]
    with pytest.raises(ValueError, match='already exists'):
        accounts.bootstrap_admin('another.admin', PASSWORD)


def test_session_rotation_expiry_and_revocation(tmp_path):
    accounts = Accounts(tmp_path / 'auth')
    accounts.bootstrap_admin('operator', PASSWORD)
    first, identity = accounts.login('operator', PASSWORD, '127.0.0.1')
    assert accounts.session(first) == identity
    second, _ = accounts.login('operator', PASSWORD, '127.0.0.1', first)
    assert accounts.session(first) is None
    with accounts.connect() as db:
        assert db.execute('SELECT token_hash FROM auth_sessions').fetchone()[0] != second
        db.execute('UPDATE auth_sessions SET expires_at=0')
    assert accounts.session(second) is None
    third, _ = accounts.login('operator', PASSWORD, '127.0.0.1')
    accounts.revoke(third)
    assert accounts.session(third) is None


def test_rejects_unknown_migration_and_public_directory(tmp_path):
    directory = tmp_path / 'auth'
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    with pytest.raises(ValueError, match='private'):
        Accounts(directory)
    directory.chmod(0o700)
    with sqlite3.connect(directory / 'accounts.sqlite3') as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(RuntimeError, match='version 99'):
        Accounts(directory)


def test_account_mutations_require_an_active_admin_session(tmp_path):
    accounts = Accounts(tmp_path / 'auth')
    admin = accounts.bootstrap_admin('operator', PASSWORD)
    with pytest.raises(PermissionError):
        accounts.create('member', PASSWORD, 'USER', admin_token=None)
    with pytest.raises(PermissionError):
        accounts.update(admin['id'], password=PASSWORD, admin_token=None)
    token, _ = accounts.login('operator', PASSWORD, '127.0.0.1')
    member = accounts.create('member', PASSWORD, 'USER', admin_token=token)
    member_token, _ = accounts.login('member', PASSWORD, '127.0.0.1')
    with pytest.raises(PermissionError):
        accounts.update(member['id'], role='ADMIN', admin_token=member_token)
    accounts.revoke(token)
    with pytest.raises(PermissionError):
        accounts.update(member['id'], enabled=False, admin_token=token)
    assert accounts.users() == [member, admin]


def test_no_shared_login_lockout_or_legacy_bucket_lockout(tmp_path):
    accounts = Accounts(tmp_path / 'auth')
    accounts.bootstrap_admin('operator', PASSWORD)
    token, _ = accounts.login('operator', PASSWORD, 'setup')
    accounts.create('member', PASSWORD, 'USER', admin_token=token)
    now = int(time.time())
    current_window = now - now % ATTEMPT_WINDOW
    source, alternate = '192.0.2.1', '192.0.2.2'
    with accounts.connect() as db:
        db.executemany('INSERT INTO login_attempts VALUES (?, ?, ?)', [
            ('global', current_window, 120),
            (f'ip:{digest(source)}', current_window, 30),
            (f'user:{digest("operator")}', current_window, 5),
        ])
    for _ in range(5):
        assert accounts.login('Operator', 'invalid', source) is None
    with pytest.raises(RateLimited):
        accounts.login('operator', PASSWORD, source)
    assert accounts.login('operator', PASSWORD, alternate)
    assert accounts.login('member', PASSWORD, source)

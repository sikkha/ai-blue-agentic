import sqlite3

import pytest

from backend.accounts import Accounts

PASSWORD = 'long test password, not a deployment credential'


def test_migration_bootstrap_and_password_storage(tmp_path):
    directory = tmp_path / 'auth'
    accounts = Accounts(directory)
    user = accounts.create('First.Admin', PASSWORD, 'ADMIN', bootstrap=True)
    assert user['username'] == 'first.admin'
    assert not user['agent_enabled']
    with accounts.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        stored = db.execute('SELECT password_hash FROM users').fetchone()[0]
        assert stored.startswith('$argon2id$') and PASSWORD not in stored
    assert Accounts(directory).users() == [user]
    with pytest.raises(ValueError, match='already exists'):
        accounts.create('another.admin', PASSWORD, 'ADMIN', bootstrap=True)


def test_session_rotation_expiry_and_revocation(tmp_path):
    accounts = Accounts(tmp_path / 'auth')
    accounts.create('member', PASSWORD, 'USER')
    first, identity = accounts.login('member', PASSWORD, '127.0.0.1')
    assert accounts.session(first) == identity
    second, _ = accounts.login('member', PASSWORD, '127.0.0.1', first)
    assert accounts.session(first) is None
    with accounts.connect() as db:
        assert db.execute('SELECT token_hash FROM auth_sessions').fetchone()[0] != second
        db.execute('UPDATE auth_sessions SET expires_at=0')
    assert accounts.session(second) is None
    third, _ = accounts.login('member', PASSWORD, '127.0.0.1')
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

"""Native web accounts and server-side sessions in an isolated SQLite database."""

import getpass
import hashlib
import re
import secrets
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

USERNAME = re.compile(r'[a-z0-9][a-z0-9_.-]{2,63}')
SESSION_SECONDS = 8 * 60 * 60
ATTEMPT_WINDOW = 15 * 60
HASHER = PasswordHasher(type=Type.ID)


class RateLimited(Exception):
    pass


def normalize_username(value: str) -> str:
    name = value.strip().lower()
    if not USERNAME.fullmatch(name):
        raise ValueError('Use 3–64 letters, numbers, periods, underscores or hyphens for the username.')
    return name


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError('Use a password between 12 and 128 characters.')
    return HASHER.hash(password)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def profile(row) -> dict:
    return {**{key: row[key] for key in ('id', 'username', 'role')},
            **{key: bool(row[key]) for key in ('enabled', 'agent_enabled')}}


class Accounts:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.stat().st_mode & 0o077:
            raise ValueError('The auth directory must be private to the service account (mode 0700).')
        self.path = self.directory / 'accounts.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                sql = Path(__file__).with_name('migrations') / '001_auth.sql'
                db.executescript(sql.read_text())
            elif version != 1:
                raise RuntimeError(f'Unsupported accounts database version {version}')
        self.path.chmod(0o600)
        self.dummy_hash = HASHER.hash(secrets.token_urlsafe(32))
        self.hash_slots = threading.BoundedSemaphore(2)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def require_admin(self, db, token):
        if token is not None and not db.execute(
            "SELECT 1 FROM auth_sessions JOIN users ON users.id=user_id "
            "WHERE token_hash=? AND expires_at>? AND enabled=1 AND role='ADMIN'",
            (digest(token), int(time.time())),
        ).fetchone():
            raise PermissionError('Administrator access required.')

    def create(self, username, password, role, agent_enabled=False, *, bootstrap=False, admin_token=None):
        username = normalize_username(username)
        hashed = password_hash(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require_admin(db, admin_token)
            if bootstrap and db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise ValueError('An account already exists. Use an administrator account to manage users.')
            try:
                cursor = db.execute('INSERT INTO users(username,password_hash,role,agent_enabled) VALUES (?,?,?,?)',
                                    (username, hashed, role, agent_enabled))
            except sqlite3.IntegrityError as error:
                raise ValueError('That username is already in use.') from error
            return profile(db.execute('SELECT * FROM users WHERE id=?', (cursor.lastrowid,)).fetchone())

    def users(self):
        with self.connect() as db:
            return [profile(row) for row in db.execute('SELECT * FROM users ORDER BY username')]

    def update(self, user_id, *, role=None, enabled=None, agent_enabled=None, password=None, admin_token=None):
        hashed = password_hash(password) if password is not None else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require_admin(db, admin_token)
            user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if user is None:
                return None
            updated_role = user['role'] if role is None else role
            active = user['enabled'] if enabled is None else enabled
            agent = user['agent_enabled'] if agent_enabled is None else agent_enabled
            if user['role'] == 'ADMIN' and user['enabled'] and (updated_role != 'ADMIN' or not active):
                if not db.execute("SELECT 1 FROM users WHERE role='ADMIN' AND enabled=1 AND id!=?", (user_id,)).fetchone():
                    raise ValueError('Keep at least one enabled administrator.')
            db.execute('UPDATE users SET role=?,enabled=?,agent_enabled=?,password_hash=? WHERE id=?',
                       (updated_role, active, agent, hashed or user['password_hash'], user_id))
            if hashed or updated_role != user['role'] or active != user['enabled'] or agent != user['agent_enabled']:
                db.execute('DELETE FROM auth_sessions WHERE user_id=?', (user_id,))
            return profile(db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())

    def charge(self, username, address, now):
        start = now - now % ATTEMPT_WINDOW
        buckets = [('global', 120), (f'ip:{digest(address)}', 30), (f'user:{digest(username)}', 5)]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE window_start < ?', (start,))
            for bucket, limit in buckets:
                row = db.execute('SELECT count FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()
                if row and row['count'] >= limit:
                    raise RateLimited
            db.executemany('INSERT INTO login_attempts VALUES (?, ?, 1) '
                           'ON CONFLICT(bucket) DO UPDATE SET count=count+1',
                           [(bucket, start) for bucket, _ in buckets])

    def login(self, username, password, address, old_token=None):
        candidate = username.strip().lower()
        now = int(time.time())
        self.charge(candidate, address, now)
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE username=? AND enabled=1', (candidate,)).fetchone()
        if not self.hash_slots.acquire(blocking=False):
            raise RateLimited
        try:
            try:
                valid = HASHER.verify(user['password_hash'] if user else self.dummy_hash, password)
            except (VerificationError, InvalidHashError):
                valid = False
        finally:
            self.hash_slots.release()
        if not valid or user is None:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = now + SESSION_SECONDS
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest = db.execute('SELECT * FROM users WHERE id=? AND enabled=1 AND password_hash=?',
                                (user['id'], user['password_hash'])).fetchone()
            if latest is None:
                return None
            db.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now,))
            if old_token:
                db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(old_token),))
            db.execute('INSERT INTO auth_sessions VALUES (?,?,?,?)', (digest(token), user['id'], csrf, expires))
        return token, {'user': profile(latest), 'csrf': csrf, 'expires_at': expires}

    def session(self, token):
        if not token or len(token) != 43:
            return None
        with self.connect() as db:
            row = db.execute('SELECT users.*, csrf, expires_at FROM auth_sessions JOIN users ON users.id=user_id '
                             'WHERE token_hash=? AND expires_at>? AND enabled=1',
                             (digest(token), int(time.time()))).fetchone()
        return {'user': profile(row), 'csrf': row['csrf'], 'expires_at': row['expires_at']} if row else None

    def revoke(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(token),))


def bootstrap(directory: Path, username: str):
    if not sys.stdin.isatty():
        raise ValueError('First-admin setup requires an interactive terminal.')
    password = getpass.getpass('New administrator password: ')
    if password != getpass.getpass('Confirm password: '):
        raise ValueError('Passwords did not match.')
    Accounts(directory).create(username, password, 'ADMIN', bootstrap=True)

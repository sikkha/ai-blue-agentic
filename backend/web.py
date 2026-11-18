"""Authenticated browser entry point. The workspace router is private to this module."""

import hmac
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from urllib.parse import urlsplit

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agentic_ai.paths import resolve
from agentic_ai.tools import registry
from backend import app as workspace
from backend.accounts import SESSION_SECONDS, Accounts, RateLimited
from launcher import cli

COOKIE = '__Host-ai_blue_session'
READS = {'GET', 'HEAD', 'OPTIONS'}
AGENT_ROUTES = ('/api/chat', '/api/uploads', '/api/approvals', '/api/turns', '/api/workspace/graph/build')
Role = Literal['ADMIN', 'USER']
Password = Annotated[str, Field(min_length=12, max_length=128)]
Username = Annotated[str, Field(min_length=3, max_length=64)]


class Credentials(BaseModel):
    username: Annotated[str, Field(max_length=64)]
    password: Annotated[str, Field(max_length=128)]


class NewUser(BaseModel):
    username: Username
    password: Password
    role: Role = 'USER'
    agent_enabled: bool = False


class UserChange(BaseModel):
    password: Password | None = None
    role: Role | None = None
    enabled: bool | None = None
    agent_enabled: bool | None = None


class Workspaces:
    def __init__(self, directory: Path, config: str):
        self.directory = directory / 'workspaces'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.config = config
        self.apps = {}
        self.lock = Lock()
        self.uploads = tempfile.TemporaryDirectory(prefix='ai-blue-uploads-')

    def app_for(self, user_id: int):
        with self.lock:
            if user_id not in self.apps:
                self.apps[user_id] = self.build(user_id)
            return self.apps[user_id]

    def build(self, user_id: int):
        root = self.directory / str(user_id)
        root.mkdir(mode=0o700, exist_ok=True)
        config = root / 'workflow.yaml'
        if not config.exists():
            base = cli.load_config(self.config)
            runtime = root / 'runtime.yaml'
            runtime.write_bytes(resolve(base.get('runtime') or 'config/runtime.yaml').read_bytes())
            reg = registry.load(base.get('registry', registry.DEFAULT_PATH))
            reg['tools'].pop('bash', None)
            tools = root / 'tools.json'
            tools.write_text(json.dumps(reg))
            base['tools'] = [name for name in base['tools'] if name in reg['tools']]
            base.update(workspace={'dir': str(root / 'notes')}, runtime=str(runtime), registry=str(tools))
            base['sandbox']['dir'] = str(root / 'sandbox')
            base.setdefault('trace', {})['path'] = str(root / 'sandbox' / 'trace.db')
            with tempfile.NamedTemporaryFile(mode='w', dir=root, delete=False) as output:
                yaml.safe_dump(base, output, allow_unicode=True)
                draft = Path(output.name)
            draft.replace(config)
        uploads = Path(self.uploads.name) / str(user_id)
        uploads.mkdir(mode=0o700, exist_ok=True)
        return workspace._create_workspace_app(str(config), uploads=uploads)


def validate_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if (not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment
            or (parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in {'localhost', '127.0.0.1'}))):
        raise ValueError('Set AIBLUE_WEB_ORIGIN to an exact HTTPS origin (HTTP is only for localhost).')
    return origin


def create_app(config: str, *, directory: Path, origin: str):
    origin = validate_origin(origin)
    accounts = Accounts(directory)
    workspaces = Workspaces(accounts.directory, config)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        workspaces.uploads.cleanup()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def validation_failure(_request, _error):
        return JSONResponse({'detail': 'Invalid request. Check the field requirements.'}, status_code=422)

    def check_origin(request: Request):
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Request origin was rejected.')

    def session(request: Request):
        token = request.cookies.get(COOKIE)
        identity = accounts.session(token)
        if identity is None:
            raise HTTPException(401, 'Sign in to continue.')
        presented = request.headers.get('x-csrf-token')
        if request.method not in READS:
            check_origin(request)
            if not hmac.compare_digest((presented or '').encode(), identity['csrf'].encode()):
                raise HTTPException(403, 'Request verification failed.')
        elif presented is not None and not hmac.compare_digest(presented.encode(), identity['csrf'].encode()):
            raise HTTPException(401, 'This browser tab belongs to a previous session.')
        return identity

    def admin(identity=Depends(session)):
        if identity['user']['role'] != 'ADMIN':
            raise HTTPException(403, 'Administrator access required.')

    @app.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith('/assets/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.post('/api/auth/login')
    def login(body: Credentials, request: Request, response: Response):
        check_origin(request)
        try:
            outcome = accounts.login(body.username, body.password, request.client.host if request.client else '',
                                     request.cookies.get(COOKIE))
        except RateLimited:
            raise HTTPException(429, 'Too many sign-in attempts. Wait before trying again.')
        if outcome is None:
            raise HTTPException(401, 'Invalid username or password.')
        token, identity = outcome
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite='strict')
        return identity

    @app.get('/api/auth/session')
    def current(identity=Depends(session)):
        return identity

    @app.post('/api/auth/logout', dependencies=[Depends(session)])
    def logout(request: Request):
        accounts.revoke(request.cookies[COOKIE])
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict')
        return response

    @app.get('/api/auth/users', dependencies=[Depends(admin)])
    def list_users():
        return accounts.users()

    @app.post('/api/auth/users', status_code=201, dependencies=[Depends(admin)])
    def create_user(body: NewUser, request: Request):
        try:
            return accounts.create(**body.model_dump(), admin_token=request.cookies[COOKIE])
        except PermissionError as error:
            raise HTTPException(403, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.patch('/api/auth/users/{user_id}', dependencies=[Depends(admin)])
    def change_user(user_id: int, body: UserChange, request: Request):
        try:
            user = accounts.update(user_id, **body.model_dump(exclude_none=True), admin_token=request.cookies[COOKIE])
        except PermissionError as error:
            raise HTTPException(403, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if user is None:
            raise HTTPException(404, 'Account not found.')
        return user

    @app.get('/')
    def index():
        path = workspace.UI_DIST / 'index.html'
        if not path.is_file():
            return PlainTextResponse('Build the frontend with npm --prefix frontend run build.', status_code=503)
        return FileResponse(path)

    if (workspace.UI_DIST / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=workspace.UI_DIST / 'assets'), name='assets')

    async def dispatch(scope, receive, send):
        if scope['type'] != 'http':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        request = Request(scope)
        path = request.url.path
        try:
            if not path.startswith('/api/'):
                raise HTTPException(404)
            identity = await run_in_threadpool(session, request)
            user = identity['user']
            if path.rstrip('/') == '/api/settings' and user['role'] != 'ADMIN':
                raise HTTPException(403, 'Administrator access required.')
            if not user['agent_enabled'] and any(path == route or path.startswith(route + '/') for route in AGENT_ROUTES):
                raise HTTPException(403, 'Agent features are not enabled for this account.')
            token = request.cookies[COOKIE]
            request.state.session_active = lambda: accounts.session(token) is not None
            private_app = await run_in_threadpool(workspaces.app_for, user['id'])
        except HTTPException as error:
            await JSONResponse({'detail': error.detail}, status_code=error.status_code)(scope, receive, send)
            return
        await private_app(scope, receive, send)

    app.mount('/', dispatch)
    return app

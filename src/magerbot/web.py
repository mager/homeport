"""Homeport's local HTTP interface. Tailscale Serve is the private HTTPS edge."""

import asyncio
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator

from .cli import get_config
from .models import Config, Model, Task
from .rpc import RPC
from .store import Store

STATIC = Path(__file__).parent / "static"
EXCLUDED = {"node_modules", "__pycache__", "dist", "vendor", "perch", "magerblog"}


class WebSettings(Model):
    origin: str = "http://127.0.0.1:8787"
    tailscale_user: str | None = None

    @field_validator("origin")
    @classmethod
    def valid_origin(cls, value):
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.netloc
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("origin must be an http(s) origin without a path")
        return value.rstrip("/")


class Submission(Model):
    id: UUID  # generated and retained by browser before a network request
    prompt: str = Field(min_length=1, max_length=200_000)
    parent_task_id: UUID | None = None
    cwd: Path | None = None
    timeout_seconds: float = Field(default=3600, gt=0, le=86400)

    @field_validator("prompt")
    @classmethod
    def not_blank(cls, text):
        if not text.strip():
            raise ValueError("Describe the task before sending")
        return text


def visible_path(path: Path) -> bool:
    return all(
        not part.startswith(".")
        and part not in EXCLUDED
        and not part.lower().startswith(("perch-", "magerblog-"))
        and not part.lower().endswith((".pem", ".key", ".p12", ".sqlite3"))
        for part in path.parts
    )


def safe_file(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not visible_path(relative):
        raise HTTPException(403, "That path is outside the file viewer")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()) or not visible_path(
        resolved.relative_to(root.resolve())
    ):
        raise HTTPException(403, "That path is outside the project")
    if not resolved.is_file():
        raise HTTPException(404, "File not found")
    if resolved.stat().st_size > 300_000:
        raise HTTPException(413, "File is too large for this viewer (300 KB limit)")
    return resolved


def create_app(
    config: Config | None = None, settings: WebSettings | None = None
) -> FastAPI:
    config = config or get_config()
    config.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings_path = config.state_dir / "web.json"
    settings = settings or (
        WebSettings.model_validate_json(settings_path.read_text())
        if settings_path.exists()
        else WebSettings()
    )
    app = FastAPI(title="Homeport", docs_url=None, redoc_url=None, openapi_url=None)
    remote_host = urlsplit(settings.origin).netloc
    local_hosts = {"127.0.0.1:8787", "localhost:8787"}

    @contextmanager
    def database():
        store = Store(config.state_dir)
        try:
            yield store
        finally:
            store.db.close()

    def task_from(store, task_id):
        try:
            return store.get(task_id)
        except ValueError:
            raise HTTPException(404, "Task not found")

    @app.middleware("http")
    async def private_access(request: Request, call_next):
        host = request.headers.get("host", "")
        local = host in local_hosts
        if host not in local_hosts | {remote_host}:
            return JSONResponse({"detail": "Unknown host"}, 403)
        # Only trust Serve's identity when arriving at our loopback listener.
        if request.client and request.client.host not in {
            "127.0.0.1",
            "::1",
            "testclient",
        }:
            return JSONResponse({"detail": "Use the private Tailscale URL"}, 403)
        if not local and (
            not settings.tailscale_user
            or request.headers.get("tailscale-user-login") != settings.tailscale_user
        ):
            return JSONResponse(
                {"detail": "Sign into the owner's Tailscale account to open Homeport"},
                403,
            )
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            expected = f"http://{host}" if local else settings.origin
            if origin != expected or request.headers.get("x-homeport-request") != "1":
                return JSONResponse(
                    {"detail": "Open Homeport directly before submitting work"}, 403
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/api/status")
    async def status():
        worker = False
        with (config.state_dir / "worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BlockingIOError:
                worker = True
        result = {
            "worker": worker,
            "codex": False,
            "account": None,
            "plan": None,
            "cwd": str(config.cwd),
        }
        try:
            async with asyncio.timeout(4):
                async with RPC(config, lambda event: None) as rpc:
                    account = (await rpc.call("account/read", {})).get("account") or {}
                    result.update(
                        codex=True,
                        account=account.get("type"),
                        plan=account.get("planType"),
                    )
        except Exception:
            pass
        return result

    @app.get("/api/tasks")
    async def tasks():
        with database() as store:
            return [task.model_dump(mode="json") for task in reversed(store.tasks())]

    @app.post("/api/tasks", status_code=202)
    async def submit(data: Submission):
        with database() as store:
            parent = (
                task_from(store, data.parent_task_id) if data.parent_task_id else None
            )
            if parent and not parent.thread_id:
                raise HTTPException(
                    409,
                    "The first task has not started yet. Wait for a conversation to be created.",
                )
            if parent and parent.state == "uncertain":
                raise HTTPException(
                    409,
                    "This task needs inspection before another turn. It has not been retried.",
                )
            try:
                task = Task(
                    id=data.id,
                    prompt=data.prompt,
                    cwd=parent.cwd if parent else (data.cwd or config.cwd),
                    thread_id=parent.thread_id if parent else None,
                    timeout_seconds=data.timeout_seconds,
                )
                return store.add(task).model_dump(mode="json")
            except ValueError as exc:
                raise HTTPException(409, str(exc))

    @app.get("/api/tasks/{task_id}")
    async def detail(task_id: UUID):
        with database() as store:
            task = task_from(store, task_id)
            related = [
                t
                for t in store.tasks()
                if t.id == task.id or (task.thread_id and t.thread_id == task.thread_id)
            ]
            return {
                "task": task.model_dump(mode="json"),
                "tasks": [t.model_dump(mode="json") for t in related],
            }

    @app.get("/api/tasks/{task_id}/conversation")
    async def conversation(task_id: UUID):
        with database() as store:
            task = task_from(store, task_id)
        if not task.thread_id:
            return {"turns": [], "status": {"type": "notLoaded"}}
        try:
            async with asyncio.timeout(8):
                async with RPC(config, lambda event: None) as rpc:
                    response = await rpc.call(
                        "thread/read",
                        {"threadId": str(task.thread_id), "includeTurns": True},
                    )
                    thread = response["thread"]
                    return {
                        "turns": thread.get("turns", []),
                        "status": thread.get("status"),
                        "name": thread.get("name"),
                    }
        except Exception:
            raise HTTPException(
                503,
                "Codex is reconnecting. Saved tasks and results are still available.",
            )

    @app.get("/api/tasks/{task_id}/files")
    async def files(task_id: UUID):
        with database() as store:
            root = task_from(store, task_id).cwd
        names = []
        truncated = False
        for folder, directories, filenames in os.walk(root, followlinks=False):
            directories[:] = sorted(
                d
                for d in directories
                if visible_path(Path(d)) and not (Path(folder) / d).is_symlink()
            )
            for filename in sorted(filenames):
                path = Path(folder) / filename
                relative = path.relative_to(root)
                if (
                    visible_path(relative)
                    and not path.is_symlink()
                    and path.stat().st_size <= 300_000
                ):
                    names.append(str(relative))
                    if len(names) >= 500:
                        truncated = True
                        break
            if truncated:
                break
        return {"files": names, "truncated": truncated}

    @app.get("/api/tasks/{task_id}/file")
    async def file(task_id: UUID, path: str):
        with database() as store:
            root = task_from(store, task_id).cwd
        resolved = safe_file(root, path)
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeError:
            raise HTTPException(415, "This viewer supports text files")
        if "\x00" in text:
            raise HTTPException(415, "This viewer supports text files")
        return {"path": path, "text": text}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve():
    import uvicorn

    os.umask(0o077)
    # Only Serve's local reverse proxy can expose this; never trust forwarded client headers.
    uvicorn.run(
        create_app(), host="127.0.0.1", port=8787, proxy_headers=False, access_log=False
    )

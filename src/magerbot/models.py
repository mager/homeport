from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Config(Model):
    state_dir: Path = Field(
        default_factory=lambda: Path.home() / ".local/state/magerbot"
    )
    cwd: Path = Field(default_factory=lambda: Path.cwd())
    codex: str = "/opt/homebrew/bin/codex"
    tmux: str = "/opt/homebrew/bin/tmux"
    rpc_timeout: float = Field(default=30, gt=0)
    poll_seconds: float = Field(default=2, gt=0)
    approval_policy: Literal["never"] = "never"
    sandbox: Literal["danger-full-access"] = "danger-full-access"

    @field_validator("state_dir", "cwd")
    @classmethod
    def absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def socket(self) -> Path:
        return self.state_dir / "codex.sock"


State = Literal[
    "queued",
    "preparing",
    "dispatching",
    "running",
    "completed",
    "failed",
    "interrupted",
    "uncertain",
]
TERMINAL = {"completed", "failed", "interrupted", "uncertain"}


class Result(Model):
    status: Literal["completed", "failed", "interrupted"]
    text: str = ""
    error: dict[str, Any] | None = None


class Task(Model):
    id: UUID = Field(default_factory=uuid4)
    prompt: str = Field(min_length=1, max_length=200_000)
    cwd: Path
    thread_id: UUID | None = None
    turn_id: str | None = None
    state: State = "queued"
    created_at: datetime = Field(default_factory=now)
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=now)
    timeout_seconds: float = Field(default=3600, gt=0)
    interrupt_requested: bool = False
    result: Result | None = None
    detail: str | None = None

    @field_validator("cwd")
    @classmethod
    def project(cls, path: Path) -> Path:
        path = path.expanduser().resolve()
        if not path.is_dir():
            raise ValueError("cwd must be an existing directory")
        if any(
            p.lower() in {"perch", "magerblog"}
            or p.lower().startswith(("perch-", "magerblog-"))
            for p in path.parts
        ):
            raise ValueError("Perch and magerblog are excluded from this harness")
        return path


class Event(Model):
    received_at: datetime = Field(default_factory=now)
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: str | int | None = None


class Turn(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    status: Literal["inProgress", "completed", "failed", "interrupted"]
    items: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None

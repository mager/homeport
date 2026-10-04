import sqlite3
from pathlib import Path
from uuid import UUID

from .models import Event, Task, now


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.db = sqlite3.connect(directory / "tasks.sqlite3", timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS archived_sessions (key TEXT PRIMARY KEY);
        """)
        (directory / "tasks.sqlite3").chmod(0o600)

    def add(self, task: Task) -> Task:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT body FROM tasks WHERE id=?", (str(task.id),)
            ).fetchone()
            if row:
                old = Task.model_validate_json(row[0])
                if (old.prompt, old.cwd, old.timeout_seconds) != (
                    task.prompt,
                    task.cwd,
                    task.timeout_seconds,
                ) or (task.thread_id is not None and task.thread_id != old.thread_id):
                    raise ValueError("Task ID already exists with different input")
                return old
            self.db.execute(
                "INSERT INTO tasks VALUES (?, ?)",
                (str(task.id), task.model_dump_json()),
            )
        return task

    def save(self, task: Task):
        task.updated_at = now()
        with self.db:
            self.db.execute(
                "UPDATE tasks SET body=? WHERE id=?",
                (task.model_dump_json(), str(task.id)),
            )

    def get(self, task_id: str | UUID) -> Task:
        row = self.db.execute(
            "SELECT body FROM tasks WHERE id=?", (str(task_id),)
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown task: {task_id}")
        return Task.model_validate_json(row[0])

    def tasks(self) -> list[Task]:
        return [
            Task.model_validate_json(r[0])
            for r in self.db.execute("SELECT body FROM tasks ORDER BY rowid")
        ]

    def archived_keys(self) -> set[str]:
        keys = {row[0] for row in self.db.execute("SELECT key FROM archived_sessions")}
        # A queued task may acquire its thread ID after it was archived.
        if keys:
            for task in self.tasks():
                if str(task.id) in keys and task.thread_id:
                    keys.add(str(task.thread_id))
        return keys

    def is_archived(self, task: Task, keys: set[str] | None = None) -> bool:
        keys = self.archived_keys() if keys is None else keys
        return str(task.id) in keys or str(task.thread_id) in keys

    def archive(self, task_id: UUID, archived: bool):
        # Separate metadata avoids overwriting task progress from the worker.
        # BEGIN IMMEDIATE also serializes this with a thread ID being assigned.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            task = self.get(task_id)
            keys = {str(task.id)}
            if task.thread_id:
                keys.add(str(task.thread_id))
                keys.update(
                    str(t.id) for t in self.tasks() if t.thread_id == task.thread_id
                )
            for key in keys:
                if archived:
                    self.db.execute(
                        "INSERT OR IGNORE INTO archived_sessions VALUES (?)", (key,)
                    )
                else:
                    self.db.execute("DELETE FROM archived_sessions WHERE key=?", (key,))

    def event(self, event: Event):
        thread_id = event.params.get("threadId") or event.params.get("thread", {}).get(
            "id"
        )
        with self.db:
            self.db.execute(
                "INSERT INTO events(thread_id,body) VALUES (?,?)",
                (thread_id, event.model_dump_json()),
            )

    def events(self, thread_id: UUID | None, after: int = 0):
        return self.db.execute(
            "SELECT seq, body FROM events WHERE thread_id=? AND seq>? ORDER BY seq",
            (str(thread_id), after),
        ).fetchall()

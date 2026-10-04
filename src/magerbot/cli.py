import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

from .models import TERMINAL, Config, Task, Turn
from .rpc import RPC
from .store import Store
from .worker import finish, run


def get_config() -> Config:
    path = Path(
        os.environ.get("MAGERBOT_CONFIG", Path.home() / ".config/magerbot/config.json")
    )
    return Config.model_validate_json(path.read_text()) if path.exists() else Config()


async def inspect_task(config, store, task, reconcile=False, turn_id=None):
    if not task.thread_id:
        raise ValueError("Task has no thread ID")
    async with RPC(config, store.event) as rpc:
        thread = (
            await rpc.call(
                "thread/read", {"threadId": str(task.thread_id), "includeTurns": True}
            )
        )["thread"]
        if reconcile:
            if turn_id:
                if task.state != "uncertain":
                    raise ValueError(
                        "Manual turn binding is only allowed for uncertain tasks"
                    )
                if not any(t["id"] == turn_id for t in thread.get("turns", [])):
                    raise ValueError("That turn does not exist in this thread")
                task.turn_id = turn_id
            if not task.turn_id:
                raise ValueError(
                    "No acknowledged turn ID. Inspect history; uncertain submissions are never retried automatically."
                )
            turn = next(
                (
                    Turn.model_validate(t)
                    for t in thread.get("turns", [])
                    if t["id"] == task.turn_id
                ),
                None,
            )
            if turn:
                if not finish(task, turn):
                    task.state = "running"
                store.save(task)
            print(task.model_dump_json(indent=2))
        else:
            print(json.dumps(thread, indent=2))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Persistent Codex tasks on the Mini")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("prompt", help="Use - to read stdin")
    submit.add_argument(
        "--id",
        type=UUID,
        help="Reuse this UUID after an uncertain SSH response; identical input is deduplicated",
    )
    submit.add_argument("--thread", type=UUID)
    submit.add_argument("--cwd", type=Path)
    submit.add_argument("--timeout", type=float, default=3600)
    sub.add_parser("worker")
    sub.add_parser("web")
    sub.add_parser("list")
    for name in ["status", "result", "events", "wait", "inspect", "reconcile", "tui"]:
        p = sub.add_parser(name)
        p.add_argument("task", type=UUID)
        if name == "reconcile":
            p.add_argument(
                "--turn",
                help="Explicitly bind an uncertain task to a verified turn from inspect",
            )
        if name == "events":
            p.add_argument("--follow", action="store_true")
        if name == "wait":
            p.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    try:
        config = get_config()
        store = Store(config.state_dir)
        if args.command == "web":
            from .web import serve

            serve()
        elif args.command == "worker":
            asyncio.run(run(config))
        elif args.command == "submit":
            task = Task(
                id=args.id or uuid4(),
                prompt=sys.stdin.read() if args.prompt == "-" else args.prompt,
                cwd=args.cwd or config.cwd,
                thread_id=args.thread,
                timeout_seconds=args.timeout,
            )
            print(store.add(task).model_dump_json(indent=2))
        elif args.command == "list":
            for task in store.tasks():
                print(
                    f"{task.id}  {task.state:12}  thread={task.thread_id}  {task.prompt[:75]!r}"
                )
        else:
            task = store.get(args.task)
            if args.command == "status":
                print(task.model_dump_json(indent=2))
            elif args.command == "result":
                print(
                    task.result.model_dump_json(indent=2)
                    if task.result
                    else task.model_dump_json(indent=2)
                )
                if task.state != "completed":
                    raise SystemExit(1)
            elif args.command == "wait":
                deadline = time.monotonic() + args.timeout
                while task.state not in TERMINAL and time.monotonic() < deadline:
                    time.sleep(1)
                    task = store.get(task.id)
                print(task.model_dump_json(indent=2))
                if task.state != "completed":
                    raise SystemExit(1)
            elif args.command == "events":
                cursor = 0
                while True:
                    task = store.get(task.id)
                    for cursor, body in store.events(task.thread_id, cursor):
                        print(body, flush=True)
                    if not args.follow or task.state in TERMINAL:
                        break
                    time.sleep(1)
            elif args.command in {"inspect", "reconcile"}:
                asyncio.run(
                    inspect_task(
                        config,
                        store,
                        task,
                        args.command == "reconcile",
                        getattr(args, "turn", None),
                    )
                )
            elif args.command == "tui":
                if not task.thread_id:
                    raise ValueError("Wait until this task has a thread ID")
                # tmux starts an argv vector, not keystrokes or a shell-built prompt.
                subprocess.run(
                    [
                        config.tmux,
                        "-L",
                        "magerbot",
                        "new-window",
                        "-t",
                        "magerbot",
                        "-n",
                        "chat",
                        "-c",
                        str(task.cwd),
                        config.codex,
                        "resume",
                        "--remote",
                        f"unix://{config.socket}",
                        str(task.thread_id),
                    ],
                    check=True,
                )
                print("Attach: tmux -L magerbot attach -t magerbot")
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"magerbot: {exc}\n")


if __name__ == "__main__":
    main()

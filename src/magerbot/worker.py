import asyncio
import fcntl

from .models import Config, Result, Task, Turn, now
from .rpc import RPC, RpcError
from .store import Store


def finish(task: Task, turn: Turn) -> bool:
    if turn.status == "inProgress":
        return False
    task.state = turn.status
    messages = [item for item in turn.items if item.get("type") == "agentMessage"]
    final = [item for item in messages if item.get("phase") == "final_answer"]
    task.result = Result(
        status=turn.status,
        text="\n".join(item.get("text", "") for item in (final or messages)),
        error=turn.error,
    )
    return True


async def observe(rpc: RPC, store: Store, task: Task):
    response = await rpc.call(
        "thread/read", {"threadId": str(task.thread_id), "includeTurns": True}
    )
    turns = response["thread"].get("turns", [])
    turn = next(
        (Turn.model_validate(t) for t in turns if t["id"] == task.turn_id), None
    )
    if turn is None:
        task.state, task.detail = (
            "uncertain",
            "Acknowledged turn absent from saved history. Inspect before continuing; no replay.",
        )
    elif finish(task, turn):
        pass
    elif (
        task.started_at
        and (now() - task.started_at).total_seconds() >= task.timeout_seconds
    ):
        if not task.interrupt_requested:
            # Persist intent BEFORE sending cancellation. It too may have an uncertain outcome.
            task.interrupt_requested = True
            task.detail = "Deadline reached; interrupt requested. This does not roll back tool effects."
            store.save(task)
            await rpc.call(
                "turn/interrupt",
                {"threadId": str(task.thread_id), "turnId": task.turn_id},
            )
        elif (now() - task.started_at).total_seconds() > task.timeout_seconds + 60:
            task.state, task.detail = (
                "uncertain",
                "Interrupt not confirmed within 60s; inspect thread.",
            )
    store.save(task)


async def dispatch(rpc: RPC, store: Store, task: Task):
    if task.thread_id and any(
        t.id != task.id and t.thread_id == task.thread_id and t.state == "uncertain"
        for t in store.tasks()
    ):
        return
    account = (await rpc.call("account/read", {})).get("account")
    if not account or account.get("type") != "chatgpt":
        if task.detail != "Waiting for ChatGPT login on the Mini":
            task.detail = "Waiting for ChatGPT login on the Mini"
            store.save(task)
        return
    task.detail = None
    task.state = "preparing"
    store.save(task)
    params = {
        "cwd": str(task.cwd),
        "approvalPolicy": "never",
        "sandbox": "danger-full-access",
    }
    if task.thread_id:
        params["threadId"] = str(task.thread_id)
        response = await rpc.call("thread/resume", params)
    else:
        params["developerInstructions"] = (
            "Work only on the requested project. Do not read or modify Perch or magerblog repositories."
        )
        response = await rpc.call("thread/start", params)
    task.thread_id = response["thread"]["id"]
    store.save(task)
    # Never deliberately steer a human's active turn. Recheck immediately before send.
    thread = (
        (
            await rpc.call(
                "thread/read", {"threadId": str(task.thread_id), "includeTurns": True}
            )
        )["thread"]
        if response["thread"].get("turns")
        else response["thread"]
    )
    if thread.get("status", {}).get("type") == "active" or any(
        t["status"] == "inProgress" for t in thread.get("turns", [])
    ):
        task.state = "queued"
        store.save(task)
        return
    task.state, task.started_at = "dispatching", now()
    store.save(task)  # crash after this point MUST NOT cause a second submission
    response = await rpc.call(
        "turn/start",
        {
            "threadId": str(task.thread_id),
            "clientUserMessageId": str(task.id),
            "input": [{"type": "text", "text": task.prompt}],
            "approvalPolicy": "never",
            "sandboxPolicy": {"type": "dangerFullAccess"},
        },
    )
    turn = Turn.model_validate(response["turn"])
    task.turn_id, task.state = turn.id, "running"
    finish(task, turn)
    store.save(task)


def recover(store: Store):
    for task in store.tasks():
        if task.state == "dispatching":
            task.state, task.detail = (
                "uncertain",
                "Worker stopped during submission; inspect events/history. No replay.",
            )
            store.save(task)
        elif task.state == "preparing":
            task.state = "queued"  # no turn was dispatched yet
            store.save(task)


async def run(config: Config):
    store = Store(config.state_dir)
    with (config.state_dir / "worker.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker is already running")
        recover(store)
        while True:
            try:
                async with RPC(config, store.event) as rpc:
                    # Subscribe to recover progress without submitting anything.
                    for task in store.tasks():
                        if task.state == "running":
                            try:
                                await rpc.call(
                                    "thread/resume", {"threadId": str(task.thread_id)}
                                )
                            except RpcError as exc:
                                task.state, task.detail = (
                                    "uncertain",
                                    f"Cannot resume acknowledged thread: {exc}. No replay.",
                                )
                                store.save(task)
                    while True:
                        active = [t for t in store.tasks() if t.state == "running"]
                        if active:
                            for task in active:
                                try:
                                    await observe(rpc, store, task)
                                except RpcError as exc:
                                    task.state, task.detail = (
                                        "uncertain",
                                        f"Cannot inspect acknowledged turn: {exc}. No replay.",
                                    )
                                    store.save(task)
                        else:
                            task = next(
                                (
                                    t
                                    for t in store.tasks()
                                    if t.state == "queued"
                                    and not any(
                                        u.state == "uncertain"
                                        and u.thread_id == t.thread_id
                                        and t.thread_id
                                        for u in store.tasks()
                                    )
                                ),
                                None,
                            )
                            if task:
                                try:
                                    await dispatch(rpc, store, task)
                                except Exception as exc:
                                    task.detail = f"{type(exc).__name__}: {exc}"
                                    task.state = (
                                        "uncertain"
                                        if task.state == "dispatching"
                                        else "failed"
                                    )
                                    store.save(task)
                                    raise
                        await asyncio.sleep(config.poll_seconds)
            except Exception as exc:
                print(
                    f"Connection/worker error: {type(exc).__name__}: {exc}; reconnecting for observation only",
                    flush=True,
                )
                await asyncio.sleep(5)

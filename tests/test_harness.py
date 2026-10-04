from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from magerbot.models import Config, Task, Turn, now
from magerbot.store import Store
from magerbot.worker import dispatch, finish, observe, recover


class FakeRPC:
    def __init__(self, responses):
        self.responses = {"account/read": {"account": {"type": "chatgpt"}}, **responses}
        self.calls = []

    async def call(self, method, params=None):
        self.calls.append((method, params))
        response = self.responses[method]
        if isinstance(response, Exception):
            raise response
        return response


def test_validation(tmp_path):
    with pytest.raises(ValidationError):
        Task(prompt="", cwd=tmp_path)
    with pytest.raises(ValidationError):
        Config(approval_policy="on-request")
    excluded = tmp_path / "perch"
    excluded.mkdir()
    with pytest.raises(ValidationError):
        Task(prompt="hello", cwd=excluded)


def test_persistence_and_idempotent_submit(tmp_path):
    store = Store(tmp_path)
    task = Task(prompt="once", cwd=tmp_path)
    store.add(task)
    task.state = "running"
    task.thread_id = uuid4()
    task.turn_id = "turn-1"
    store.save(task)
    reopened = Store(tmp_path)
    assert (
        reopened.add(Task(id=task.id, prompt="once", cwd=tmp_path)).turn_id == "turn-1"
    )
    assert len(reopened.tasks()) == 1
    with pytest.raises(ValueError):
        reopened.add(Task(id=task.id, prompt="different", cwd=tmp_path))


async def test_dispatch_ack_loss_is_persisted_before_send(tmp_path):
    store = Store(tmp_path)
    task = store.add(Task(prompt="change a file", cwd=tmp_path))
    rpc = FakeRPC(
        {
            "thread/start": {
                "thread": {"id": str(uuid4()), "status": {"type": "idle"}}
            },
            "turn/start": TimeoutError("lost acknowledgement"),
        }
    )
    with pytest.raises(TimeoutError):
        await dispatch(rpc, store, task)
    assert store.get(task.id).state == "dispatching"
    assert store.get(task.id).thread_id is not None
    assert [c[0] for c in rpc.calls].count("turn/start") == 1


async def test_restart_observation_does_not_replay(tmp_path):
    store = Store(tmp_path)
    task = store.add(
        Task(
            prompt="one write",
            cwd=tmp_path,
            thread_id=uuid4(),
            turn_id="saved",
            state="running",
        )
    )
    rpc = FakeRPC(
        {
            "thread/read": {
                "thread": {
                    "turns": [
                        {
                            "id": "saved",
                            "status": "completed",
                            "items": [
                                {
                                    "type": "agentMessage",
                                    "phase": "commentary",
                                    "text": "working",
                                },
                                {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "done",
                                },
                            ],
                        }
                    ]
                }
            }
        }
    )
    await observe(rpc, store, task)
    assert task.result.text == "done"
    assert task.state == "completed"
    assert [c[0] for c in rpc.calls] == ["thread/read"]


async def test_active_interactive_turn_waits(tmp_path):
    store = Store(tmp_path)
    task = store.add(Task(prompt="follow up", cwd=tmp_path, thread_id=uuid4()))
    rpc = FakeRPC(
        {
            "thread/resume": {
                "thread": {
                    "id": str(task.thread_id),
                    "status": {"type": "active"},
                    "turns": [],
                }
            }
        }
    )
    await dispatch(rpc, store, task)
    assert task.state == "queued"
    assert not any(c[0] == "turn/start" for c in rpc.calls)


async def test_missing_turn_is_uncertain(tmp_path):
    store = Store(tmp_path)
    task = store.add(
        Task(
            prompt="run",
            cwd=tmp_path,
            thread_id=uuid4(),
            turn_id="missing",
            state="running",
        )
    )
    await observe(FakeRPC({"thread/read": {"thread": {"turns": []}}}), store, task)
    assert task.state == "uncertain"
    assert task.result is None


async def test_timeout_interrupt_once_and_confirm(tmp_path):
    store = Store(tmp_path)
    task = store.add(
        Task(
            prompt="slow",
            cwd=tmp_path,
            thread_id=uuid4(),
            turn_id="slow",
            state="running",
            timeout_seconds=1,
            started_at=now() - timedelta(seconds=2),
        )
    )
    rpc = FakeRPC(
        {
            "thread/read": {
                "thread": {"turns": [{"id": "slow", "status": "inProgress"}]}
            },
            "turn/interrupt": {},
        }
    )
    await observe(rpc, store, task)
    await observe(rpc, store, task)
    assert sum(c[0] == "turn/interrupt" for c in rpc.calls) == 1
    rpc.responses["thread/read"]["thread"]["turns"][0]["status"] = "interrupted"
    await observe(rpc, store, task)
    assert task.state == "interrupted"


async def test_unknown_submission_blocks_followup(tmp_path):
    store = Store(tmp_path)
    thread_id = uuid4()
    store.add(
        Task(prompt="unknown", cwd=tmp_path, thread_id=thread_id, state="uncertain")
    )
    task = store.add(Task(prompt="followup", cwd=tmp_path, thread_id=thread_id))
    rpc = FakeRPC({})
    await dispatch(rpc, store, task)
    assert not rpc.calls
    assert task.state == "queued"


def test_failure_is_not_success(tmp_path):
    task = Task(prompt="run", cwd=tmp_path)
    assert finish(task, Turn(id="a", status="failed", error={"message": "quota"}))
    assert task.result.status == "failed"
    assert task.result.error["message"] == "quota"


def test_crash_recovery_preserves_running_and_quarantines_dispatch(tmp_path):
    store = Store(tmp_path)
    tasks = [
        store.add(Task(prompt=state, cwd=tmp_path, state=state))
        for state in ["queued", "preparing", "dispatching", "running"]
    ]
    recover(Store(tmp_path))
    assert [store.get(t.id).state for t in tasks] == [
        "queued",
        "queued",
        "uncertain",
        "running",
    ]


async def test_no_api_billing_fallback(tmp_path):
    store = Store(tmp_path)
    task = store.add(Task(prompt="hello", cwd=tmp_path))
    rpc = FakeRPC({"account/read": {"account": {"type": "apiKey"}}})
    await dispatch(rpc, store, task)
    assert task.state == "queued"
    assert [c[0] for c in rpc.calls] == ["account/read"]

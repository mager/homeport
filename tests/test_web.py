from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient

from magerbot.models import Config, Task
from magerbot.store import Store
from magerbot.web import WebSettings, create_app


def client(tmp_path, remote=False):
    config = Config(cwd=tmp_path, state_dir=tmp_path / "state")
    settings = WebSettings(
        origin="https://mini.example.ts.net:9443", tailscale_user="owner@example.com"
    )
    app = create_app(config, settings)
    return TestClient(
        app,
        base_url="https://mini.example.ts.net:9443"
        if remote
        else "http://127.0.0.1:8787",
    ), config


def headers():
    return {"Origin": "http://127.0.0.1:8787", "X-Homeport-Request": "1"}


def test_remote_requires_owner_identity(tmp_path):
    c, _ = client(tmp_path, True)
    assert c.get("/api/tasks").status_code == 403
    assert (
        c.get(
            "/api/tasks", headers={"Tailscale-User-Login": "stranger@example.com"}
        ).status_code
        == 403
    )
    assert (
        c.get(
            "/api/tasks", headers={"Tailscale-User-Login": "owner@example.com"}
        ).status_code
        == 200
    )


def test_cross_origin_and_dns_rebinding_blocked(tmp_path):
    c, _ = client(tmp_path)
    data = {"id": str(uuid4()), "prompt": "hello"}
    assert c.post("/api/tasks", json=data).status_code == 403
    assert (
        c.post(
            "/api/tasks",
            json=data,
            headers={**headers(), "Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert c.get("/api/tasks", headers={"Host": "evil.example"}).status_code == 403
    assert c.post("/api/tasks", json=data, headers=headers()).status_code == 202


def test_duplicate_and_followup_preserve_thread(tmp_path):
    c, config = client(tmp_path)
    payload = {"id": str(uuid4()), "prompt": "Do work"}
    first = c.post("/api/tasks", json=payload, headers=headers())
    assert first.status_code == 202
    store = Store(config.state_dir)
    task = store.get(payload["id"])
    task.thread_id = uuid4()
    task.state = "completed"
    store.save(task)
    assert c.post("/api/tasks", json=payload, headers=headers()).json()[
        "thread_id"
    ] == str(task.thread_id)
    assert len(c.get("/api/tasks").json()) == 1
    follow = c.post(
        "/api/tasks",
        json={
            "id": str(uuid4()),
            "prompt": "Continue",
            "parent_task_id": payload["id"],
        },
        headers=headers(),
    )
    assert follow.status_code == 202
    assert follow.json()["thread_id"] == str(task.thread_id)
    assert follow.json()["cwd"] == str(tmp_path)
    assert (
        c.post(
            "/api/tasks", json={**payload, "prompt": "different"}, headers=headers()
        ).status_code
        == 409
    )


def test_files_cannot_escape_project_or_read_hidden(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "hello.py").write_text('print("hello")')
    (root / ".env").write_text("SECRET=value")
    (tmp_path / "outside.txt").write_text("outside")
    (root / "outside-link.txt").symlink_to(tmp_path / "outside.txt")
    c, _ = client(root)
    task = c.post(
        "/api/tasks", json={"id": str(uuid4()), "prompt": "inspect"}, headers=headers()
    ).json()
    base = "/api/tasks/" + task["id"]
    assert (
        c.get(base + "/file", params={"path": "hello.py"}).json()["text"]
        == 'print("hello")'
    )
    for path in [
        "../outside.txt",
        ".env",
        "outside-link.txt",
        str(tmp_path / "outside.txt"),
    ]:
        assert c.get(base + "/file", params={"path": path}).status_code == 403
    assert ".env" not in c.get(base + "/files").json()["files"]
    assert "outside-link.txt" not in c.get(base + "/files").json()["files"]


def test_unknown_and_validation(tmp_path):
    c, _ = client(tmp_path)
    assert c.get("/api/tasks/" + str(uuid4())).status_code == 404
    assert (
        c.post(
            "/api/tasks", json={"id": str(uuid4()), "prompt": " "}, headers=headers()
        ).status_code
        == 422
    )
    response = c.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_concurrent_same_id_is_one_task(tmp_path):
    task = Task(prompt="only once", cwd=tmp_path)
    Store(tmp_path).db.close()

    def write(_):
        store = Store(tmp_path)
        try:
            return store.add(task).id
        finally:
            store.db.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(write, range(8))) == [task.id] * 8
    assert len(Store(tmp_path).tasks()) == 1


def test_archive_restores_whole_thread_and_preserves_history(tmp_path):
    c, config = client(tmp_path)
    store = Store(config.state_dir)
    thread = uuid4()
    first = store.add(
        Task(prompt="first", cwd=tmp_path, thread_id=thread, state="completed")
    )
    follow = store.add(
        Task(prompt="follow", cwd=tmp_path, thread_id=thread, state="completed")
    )
    endpoint = f"/api/tasks/{first.id}/archive"
    assert c.put(endpoint, json={"archived": True}).status_code == 403
    assert (
        c.put(endpoint, json={"archived": True}, headers=headers()).status_code == 200
    )
    assert all(t["archived"] for t in c.get("/api/tasks").json())
    # New DB/application connection observes metadata, with all results intact.
    c2, _ = client(tmp_path)
    assert len(c2.get(f"/api/tasks/{first.id}").json()["tasks"]) == 2
    payload = {"id": str(uuid4()), "prompt": "more", "parent_task_id": str(follow.id)}
    assert c2.post("/api/tasks", json=payload, headers=headers()).status_code == 409
    assert (
        c2.put(
            f"/api/tasks/{follow.id}/archive",
            json={"archived": False},
            headers=headers(),
        ).status_code
        == 200
    )
    assert not any(t["archived"] for t in c2.get("/api/tasks").json())
    assert c2.post("/api/tasks", json=payload, headers=headers()).status_code == 202
    store.db.close()


def test_archive_queued_task_survives_worker_assignment_and_retry(tmp_path):
    c, config = client(tmp_path)
    payload = {"id": str(uuid4()), "prompt": "run once"}
    c.post("/api/tasks", json=payload, headers=headers())
    store = Store(config.state_dir)
    task = store.get(payload["id"])
    endpoint = f"/api/tasks/{task.id}/archive"
    c.put(endpoint, json={"archived": True}, headers=headers())
    # Worker saves a record read before archiving. It must not unarchive it.
    task.thread_id = uuid4()
    task.state = "running"
    store.save(task)
    assert c.get("/api/tasks").json()[0]["archived"] is True
    assert c.get("/api/tasks").json()[0]["state"] == "running"
    assert c.post("/api/tasks", json=payload, headers=headers()).status_code == 202
    assert len(store.tasks()) == 1
    c.put(endpoint, json={"archived": False}, headers=headers())
    assert not c.get("/api/tasks").json()[0]["archived"]
    store.db.close()

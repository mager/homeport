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

"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  tasks: [],
  selected: null,
  status: null,
  busy: false,
  signature: "",
  pending: null,
  files: false,
  polling: false,
  archived: false,
  archiving: false,
};
const labels = {
  queued: "Queued",
  preparing: "Starting",
  dispatching: "Sending",
  running: "Working",
  completed: "Done",
  failed: "Failed",
  interrupted: "Stopped",
  uncertain: "Needs attention",
};
const active = new Set(["queued", "preparing", "dispatching", "running"]);
function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}
function error(text) {
  $("submit-error").textContent = text;
  $("submit-error").hidden = !text;
}
async function api(path, options = {}) {
  const res = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Homeport-Request": "1",
      ...options.headers,
    },
    signal: AbortSignal.timeout(15000),
  });
  const body = await res.json();
  if (!res.ok) {
    const e = new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Please check the task and project folder.",
    );
    e.status = res.status;
    throw e;
  }
  return body;
}
function chosen() {
  return state.tasks.find((t) => t.id === state.selected);
}
function family() {
  const t = chosen();
  return t
    ? state.tasks
        .filter(
          (x) => x.id === t.id || (t.thread_id && x.thread_id === t.thread_id),
        )
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
    : [];
}
function newest() {
  return family().at(-1) || chosen();
}
function age(date) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(date)) / 60000),
  );
  return minutes < 1
    ? "now"
    : minutes < 60
      ? minutes + "m"
      : minutes < 1440
        ? Math.floor(minutes / 60) + "h"
        : new Date(date).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          });
}
function renderList() {
  const groups = new Map();
  for (const t of [...state.tasks].reverse()) {
    const key = t.thread_id || t.id;
    const g = groups.get(key);
    if (g) g.latest = t;
    else groups.set(key, { first: t, latest: t });
  }
  const signature = JSON.stringify([
    state.selected,
    state.archived,
    [...groups.values()].map((g) => [
      g.first.id,
      g.first.thread_id,
      g.latest.id,
      g.latest.state,
      g.latest.archived,
      age(g.latest.updated_at),
    ]),
  ]);
  if (signature === state.listSignature) return;
  state.listSignature = signature;
  const list = $("task-list");
  list.replaceChildren();
  const visible = [...groups.values()].filter(
    (g) => !!g.latest.archived === state.archived,
  );
  $("task-count").textContent = visible.length || "";
  $("active-sessions").setAttribute("aria-pressed", String(!state.archived));
  $("archived-sessions").setAttribute("aria-pressed", String(state.archived));
  if (!visible.length) {
    list.append(
      el(
        "p",
        "subtle",
        state.archived
          ? "No archived conversations. Archive a session to clear it from Active."
          : "No active conversations. Start a task or reopen one from Archived.",
      ),
    );
    return;
  }
  const selected = chosen();
  for (const { first, latest } of visible.sort((a, b) =>
    b.latest.created_at.localeCompare(a.latest.created_at),
  )) {
    const button = el("button", "task-row");
    button.classList.toggle(
      "selected",
      !!selected &&
        (selected.id === first.id ||
          (first.thread_id && selected.thread_id === first.thread_id)),
    );
    button.setAttribute(
      "aria-current",
      button.classList.contains("selected") ? "page" : "false",
    );
    button.append(el("span", "task-title", first.prompt.split("\n")[0]));
    const meta = el("span", "task-meta");
    meta.append(
      el("span", "status-dot " + latest.state),
      el("span", "", labels[latest.state] || latest.state),
      el("span", "task-time", age(latest.updated_at)),
    );
    button.append(meta);
    button.onclick = () => select(latest.id);
    list.append(button);
  }
}
function setMobile(open) {
  $("sidebar").classList.toggle("open", open);
  $("menu").setAttribute("aria-expanded", String(open));
  $("menu").setAttribute(
    "aria-label",
    open ? "Hide conversations" : "Show conversations",
  );
}
function select(id) {
  if (state.pending) {
    error(
      "A submission is waiting for confirmation. Use “Check submission” before switching conversations.",
    );
    return;
  }
  if (state.selected !== id) toggleFiles(false);
  state.selected = id;
  if (!id) state.archived = false;
  else if (chosen()) state.archived = !!chosen().archived;
  state.signature = "";
  location.hash = id ? "task=" + id : "";
  setMobile(false);
  error("");
  $("prompt").value =
    localStorage.getItem("homeport.draft." + (id || "new")) || "";
  $("welcome").hidden = !!id;
  $("conversation").hidden = !id;
  $("files-toggle").hidden = !id;
  $("archive-session").hidden = !id;
  $("project-settings").hidden = !!id;
  $("task-notice").hidden = true;
  if (!id) {
    $("conversation").replaceChildren();
    $("view-title").textContent = "New task";
    toggleFiles(false);
  } else {
    $("conversation").replaceChildren(
      el("p", "subtle", "Loading the conversation…"),
    );
  }
  renderList();
  updateComposer();
  refreshConversation();
}
function updateComposer() {
  const task = newest();
  const waiting = task && active.has(task.state);
  const archived = !!task?.archived;
  $("archive-session").textContent = archived ? "Restore" : "Archive";
  $("archive-session").title = archived
    ? "Return this conversation to Active"
    : "Hide this conversation. Running work continues.";
  $("archive-session").disabled =
    state.archiving || state.busy || !!state.pending;
  $("send").disabled =
    state.busy ||
    (!state.pending &&
      (archived || !!(task && !task.thread_id) || task?.state === "uncertain"));
  $("send").replaceChildren(
    document.createTextNode(
      state.busy
        ? "Sending…"
        : state.pending
          ? "Check submission"
          : archived
            ? "Archived"
            : state.selected
              ? waiting
                ? "Queue follow-up"
                : "Send follow-up"
              : "Start task",
    ),
    el("span", "", "↑"),
  );
  $("prompt").disabled = archived || !!state.pending;
  $("composer-context").textContent = waiting
    ? "Runs after the current task"
    : "Same conversation";
  $("prompt").placeholder = state.selected
    ? "What should we do next?"
    : "What are we working on?";
  const path = task?.cwd || state.status?.cwd;
  if (path) {
    $("project").textContent = path.split("/").filter(Boolean).at(-1);
    $("project").title = path;
  }
}
function prose(text) {
  const box = el("div");
  // Fence handling is deliberately text-only: model HTML never becomes executable markup.
  if (String(text || "").includes("```")) {
    const chunks = String(text).split("```");
    chunks.forEach((chunk, i) => {
      if (!chunk.trim()) return;
      if (i % 2) {
        const n = el("pre", "", chunk.replace(/^[\w+-]*\n/, ""));
        n.tabIndex = 0;
        box.append(n);
      } else appendParagraphs(box, chunk);
    });
  } else appendParagraphs(box, text || "");
  return box;
}
function appendParagraphs(box, text) {
  for (const block of String(text).split(/\n\s*\n/)) {
    if (!block.trim()) continue;
    if (/^#{1,3} /.test(block)) {
      box.append(el("h3", "", block.replace(/^#{1,3} /, "")));
    } else box.append(el("p", "", block));
  }
}
function message(role, text) {
  const n = el("article", "message " + role);
  const label = el("div", "message-label");
  if (role === "agent") {
    const icon = el("img");
    icon.src = "/static/icon.svg";
    icon.alt = "";
    label.append(icon);
  }
  label.append(document.createTextNode(role === "user" ? "You" : "Codex"));
  n.append(label, prose(text));
  return n;
}
function tool(item) {
  const details = el("details", "tool");
  details.dataset.item = item.id;
  const title =
    item.type === "fileChange" ? "Changed files" : item.command || "Command";
  details.append(el("summary", "", title));
  let text = item.aggregatedOutput || "";
  if (item.type === "fileChange")
    text = (item.changes || [])
      .map((c) => c.path + "\n" + (c.diff || ""))
      .join("\n\n");
  if (!text)
    text = item.status === "inProgress" ? "Running on the Mini…" : "Completed";
  details.append(el("pre", "", text));
  return details;
}
function renderConversation(data, fallback = false) {
  const tasks = family();
  const signature = JSON.stringify([
    data,
    tasks.map((t) => [t.id, t.state, t.result, t.detail, t.archived]),
  ]);
  if (signature === state.signature) return;
  state.signature = signature;
  const column = document.querySelector(".conversation-column");
  const nearBottom =
    column.scrollHeight - column.scrollTop - column.clientHeight < 140;
  const opened = new Set(
    [...document.querySelectorAll(".tool[open]")].map((n) => n.dataset.item),
  );
  const list = $("conversation");
  list.replaceChildren();
  const represented = new Set();
  if (data?.turns?.length) {
    for (const turn of data.turns) {
      represented.add(turn.id);
      for (const item of turn.items || []) {
        if (item.type === "userMessage") {
          const text = (item.content || []).map((x) => x.text || "").join("\n");
          if (text) list.append(message("user", text));
        } else if (item.type === "agentMessage" && item.text)
          list.append(message("agent", item.text));
        else if (["commandExecution", "fileChange"].includes(item.type)) {
          const t = tool(item);
          t.open = opened.has(item.id);
          list.append(t);
        }
      }
      const end = el("div", "turn-end");
      end.append(
        el(
          "span",
          "status-dot " +
            (turn.status === "inProgress" ? "running" : turn.status),
        ),
        document.createTextNode(
          turn.status === "inProgress"
            ? "Working on the Mini…"
            : turn.status === "completed"
              ? "Completed"
              : turn.status,
        ),
      );
      list.append(end);
    }
  }
  for (const task of tasks) {
    if (task.turn_id && represented.has(task.turn_id)) continue;
    list.append(message("user", task.prompt));
    if (task.result?.text) list.append(message("agent", task.result.text));
    else
      list.append(
        el("p", "subtle", task.detail || labels[task.state] || task.state),
      );
  }
  if (!list.children.length)
    list.append(
      el(
        "p",
        "subtle",
        "Waiting for Codex to begin. This task is saved on the Mini.",
      ),
    );
  $("view-title").textContent =
    data?.name || tasks[0]?.prompt.split("\n")[0] || "Conversation";
  const latest = tasks.at(-1);
  const notice = latest?.archived
    ? "Archived. History is saved and any running work continues. Restore to send another message."
    : latest?.state === "uncertain"
      ? "The connection was lost during submission. Homeport has not repeated the task. Inspect its outcome before continuing."
      : latest?.result?.error?.message || latest?.detail || "";
  $("task-notice").textContent = notice;
  $("task-notice").hidden = !notice;
  if (nearBottom) column.scrollTop = column.scrollHeight;
}
async function refreshConversation() {
  if (!state.selected) return;
  const selected = state.selected;
  try {
    const data = await api("/tasks/" + selected + "/conversation");
    if (selected === state.selected) renderConversation(data);
  } catch (e) {
    if (selected === state.selected) {
      renderConversation(null, true);
      $("connection-banner").textContent = e.message;
      $("connection-banner").hidden = false;
    }
  }
}
async function poll() {
  if (state.polling) return;
  state.polling = true;
  try {
    state.tasks = await api("/tasks");
    $("connection-banner").hidden = true;
    renderList();
    updateComposer();
    await refreshConversation();
  } catch (e) {
    $("connection-banner").textContent =
      "Connection interrupted. Work stays on the Mini. Reconnecting…";
    $("connection-banner").hidden = false;
  } finally {
    state.polling = false;
    setTimeout(poll, 2500);
  }
}
async function health() {
  try {
    state.status = await api("/status");
    const ok =
      state.status.worker &&
      state.status.codex &&
      state.status.account === "chatgpt";
    $("host-dot").className = "status-dot " + (ok ? "online" : "offline");
    $("host-status").textContent = ok
      ? "Your Mini is ready"
      : "Mini needs attention";
    $("host-detail").textContent = ok
      ? "Codex " + (state.status.plan || "ChatGPT") + " · private connection"
      : !state.status.codex
        ? "Waiting for Codex"
        : !state.status.worker
          ? "Task worker is offline"
          : "ChatGPT sign-in needed";
    if (!$("cwd").value) $("cwd").value = state.status.cwd;
    updateComposer();
  } catch (e) {
    $("host-status").textContent = "Reconnecting to your Mini";
    $("host-dot").className = "status-dot offline";
  } finally {
    setTimeout(health, 15000);
  }
}
$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy) return;
  error("");
  const prior = state.pending;
  if (!state.pending) {
    const prompt = $("prompt").value.trim();
    if (!prompt) return;
    state.pending = {
      id: crypto.randomUUID(),
      prompt,
      parent_task_id: state.selected,
      cwd: state.selected ? null : $("cwd").value || null,
    };
    localStorage.setItem("homeport.pending", JSON.stringify(state.pending));
  }
  state.busy = true;
  updateComposer();
  try {
    let task;
    if (prior) {
      try {
        task = (await api("/tasks/" + prior.id)).task;
      } catch (e) {
        if (e.status !== 404) throw e;
      }
    }
    if (!task)
      task = await api("/tasks", {
        method: "POST",
        body: JSON.stringify(state.pending),
      });
    localStorage.removeItem("homeport.draft." + (state.selected || "new"));
    state.pending = null;
    localStorage.removeItem("homeport.pending");
    state.tasks = [task, ...state.tasks.filter((t) => t.id !== task.id)];
    $("prompt").value = "";
    state.busy = false;
    select(task.id);
  } catch (e) {
    if (e.status && e.status < 500) {
      state.pending = null;
      localStorage.removeItem("homeport.pending");
      error(e.message);
    } else
      error(
        "No confirmation yet. Your request ID is saved. Use “Check submission” to safely reconnect without creating a duplicate.",
      );
  } finally {
    state.busy = false;
    updateComposer();
  }
});
$("prompt").addEventListener("input", () =>
  localStorage.setItem(
    "homeport.draft." + (state.selected || "new"),
    $("prompt").value,
  ),
);
$("prompt").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    $("composer").requestSubmit();
  }
});
for (const [id, archived] of [
  ["active-sessions", false],
  ["archived-sessions", true],
]) {
  $(id).onclick = () => {
    state.archived = archived;
    renderList();
  };
}
$("archive-session").onclick = async () => {
  if (!state.selected || state.pending || state.archiving) return;
  const id = state.selected;
  const archived = !chosen()?.archived;
  state.archiving = true;
  error("");
  updateComposer();
  try {
    await api("/tasks/" + id + "/archive", {
      method: "PUT",
      body: JSON.stringify({ archived }),
    });
    state.tasks = await api("/tasks");
    if (state.selected === id) {
      if (archived) {
        select(null);
        state.archived = false;
      } else {
        state.archived = false;
        state.signature = "";
        await refreshConversation();
      }
    }
    renderList();
  } catch (e) {
    error(
      "Could not confirm the archive change. Refresh or try again; history is saved. " +
        e.message,
    );
  } finally {
    state.archiving = false;
    updateComposer();
  }
};
$("new-task").onclick = () => {
  select(null);
  $("prompt").focus();
};
$("menu").onclick = () => setMobile(!$("sidebar").classList.contains("open"));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    select(null);
    $("prompt").focus();
  }
  if (e.key === "Escape") {
    setMobile(false);
    toggleFiles(false);
  }
});
for (const b of document.querySelectorAll("[data-prompt]"))
  b.onclick = () => {
    $("prompt").value = b.dataset.prompt;
    $("prompt").focus();
  };
async function toggleFiles(open) {
  state.files = open;
  $("file-panel").hidden = !open;
  $("files-toggle").setAttribute("aria-expanded", String(open));
  if (!open || !state.selected) return;
  $("file-viewer").hidden = true;
  $("file-list").hidden = false;
  $("file-list").replaceChildren(el("p", "subtle", "Loading files…"));
  try {
    const selected = state.selected;
    const data = await api("/tasks/" + selected + "/files");
    if (selected !== state.selected) return;
    $("file-list").replaceChildren();
    for (const path of data.files) {
      const b = el("button", "", path);
      b.onclick = () => showFile(path);
      $("file-list").append(b);
    }
    if (!data.files.length)
      $("file-list").append(
        el("p", "subtle", "No readable project files yet."),
      );
    if (data.truncated)
      $("file-list").append(el("p", "subtle", "Showing the first 500 files."));
  } catch (e) {
    $("file-list").replaceChildren(el("p", "subtle", e.message));
  }
}
async function showFile(path) {
  try {
    const selected = state.selected;
    const data = await api(
      "/tasks/" + selected + "/file?path=" + encodeURIComponent(path),
    );
    if (selected !== state.selected) return;
    $("file-list").hidden = true;
    $("file-viewer").hidden = false;
    $("file-name").textContent = data.path;
    $("file-content").textContent = data.text;
  } catch (e) {
    error(e.message);
  }
}
$("files-toggle").onclick = () => toggleFiles(!state.files);
$("files-close").onclick = () => toggleFiles(false);
$("file-back").onclick = () => toggleFiles(true);
window.addEventListener("hashchange", () => {
  const id = new URLSearchParams(location.hash.slice(1)).get("task");
  if (id !== state.selected) select(id);
});
(async () => {
  try {
    state.tasks = await api("/tasks");
    select(new URLSearchParams(location.hash.slice(1)).get("task"));
    const pending = JSON.parse(
      localStorage.getItem("homeport.pending") || "null",
    );
    if (pending) {
      state.pending = pending;
      $("prompt").value = pending.prompt;
      error(
        "A previous submission is waiting for confirmation. Use “Check submission” to find it or send it once.",
      );
      updateComposer();
    }
  } catch (e) {
    error("The Mini is not reachable yet. Reconnecting…");
  }
  poll();
  health();
})();

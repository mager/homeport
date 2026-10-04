const states = {
  start: {
    client: "Laptop connected",
    note: "task submitted",
    link: "TAILSCALE",
    mini: "Codex working",
    title: "Task accepted. Conversation saved.",
    detail: "The worker tracks the turn on the Mini.",
  },
  leave: {
    client: "Laptop disconnected",
    note: "go do your thing",
    link: "OFFLINE",
    mini: "Still working",
    title: "Connection closed. Work continues.",
    detail: "The Mini keeps running the same turn. Nothing is resubmitted.",
  },
  return: {
    client: "Back from any device",
    note: "same conversation",
    link: "RECONNECTED",
    mini: "Result saved",
    title: "Welcome back. Pick up the thread.",
    detail: "Read the result, review the files, and send a follow-up.",
  },
};
const demo = document.querySelector(".connection-demo");
for (const button of document.querySelectorAll("button[data-step]")) {
  button.addEventListener("click", () => {
    const step = button.dataset.step,
      value = states[step];
    demo.dataset.step = step;
    for (const other of demo.querySelectorAll("button"))
      other.setAttribute("aria-pressed", String(other === button));
    for (const [id, key] of [
      ["client-label", "client"],
      ["client-note", "note"],
      ["link-label", "link"],
      ["mini-label", "mini"],
      ["demo-title", "title"],
      ["demo-detail", "detail"],
    ])
      document.getElementById(id).textContent = value[key];
  });
}
const copy = document.getElementById("copy-install");
copy.addEventListener("click", async () => {
  const feedback = document.getElementById("copy-feedback");
  try {
    await navigator.clipboard.writeText(
      document.getElementById("install-command").textContent,
    );
    feedback.textContent = "Copied. Paste into your Mini’s terminal.";
    copy.textContent = "Copied ✓";
  } catch {
    feedback.textContent = "Select and copy the two commands above.";
  }
});

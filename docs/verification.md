# Verified behavior

Checked October 4, 2026 against Codex CLI 0.160.0 on an Apple Silicon Mac mini running macOS 27.0.1.

- ChatGPT authentication reported plan type `pro`; no API key was provided.
- App-server confirmed `approvalPolicy: never` and sandbox `dangerFullAccess`.
- A real Codex task used Python to write a text file, then read it back.
- A follow-up remembered context from the preceding turn.
- During a 25-second command, the Python worker was terminated and automatically restarted. It observed the existing turn to completion; the append-only test file contained exactly one line.
- With the TUI connected to the same Unix socket, a harness-submitted prompt and live progress appeared in the terminal.
- A real SSH attachment was abruptly killed. Reconnecting showed unchanged server, worker, and TUI process IDs. This tests transport disconnect, not physically closing the laptop or rebooting the Mini.
- `codex queue --remote unix://…` delivered a follow-up to that same conversation.
- A browser task and a browser follow-up both completed. Reloading preserved the conversation and results.
- Project file preview worked through the private HTTPS URL.
- The 390 × 844 phone layout had no horizontal overflow. This is browser viewport testing, not a completed test on a physical iPhone.
- 19 automated tests cover task validation, durable state, idempotent concurrent submissions, restart reconciliation, timeout interruption, uncertain outcomes, API-account refusal, private web access, cross-origin writes, host validation, file boundaries, and archive/restore persistence while a worker updates a task.

## Limits

The app-server protocol is experimental. Re-test when upgrading Codex.

Launchd loads this installation at the user's macOS login. Unattended boot, FileVault unlock, and OS logout recovery have not been tested or provisioned.

The worker checks for an active interactive turn, but there is no atomic idle-and-start reservation across independent clients in this implementation. Avoid submitting from the CLI and browser at precisely the same instant.

File review is read-only. This release does not include a full browser IDE, browser terminal, push notifications, or multi-user collaboration. Work is serialized through one worker. A queued follow-up to a busy CLI thread can hold up later queued work.

A separate app-server is not an attachment mechanism. Live conversation sharing requires both clients to use the exact same server endpoint.

## Fast workspace verification

- Live browser: search by prompt, arrow-key selection and Enter, Cmd K search, Cmd Shift K new session, and per-session draft recovery after reload.
- Conversation scrollback and Latest output checked with a stationary composer.
- Desktop and 390px phone viewport checked; reduced-motion emulation disabled transition and animation styles. Physical phone performance remains unverified.
- A real no-tools task returned `Fast workspace ready.` through the updated composer, then was archived from the filtered mobile sidebar.

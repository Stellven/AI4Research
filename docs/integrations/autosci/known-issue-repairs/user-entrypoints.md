# User entrypoint and TMUX repair closeout

## What is verified

- **CLI:** `solar harness intake --no-dispatch` creates a real sprint contract.
- **GUI control plane:** `POST /intake` invokes the same production intake command, stores the request record, returns the sprint ID, and exposes that sprint through `/sprints`.
- **TUI:** `solar ui --once --no-color` reads the same isolated runtime and lists the created run state. It is an inspection TUI, not a task-submission client.
- **TMUX:** the WSL journey creates two real tmux sessions, sends distinct input, captures distinct output, respawns one pane, and kills both sessions.
- **Remote monitor:** the cmux renderer is covered by a controlled transport plan. Remote command arguments are shell-escaped. This is not evidence of a reachable remote host.

## Explicit limits

- The immutable `harness/lib/symphony/status-server.py` still owns production port range **8765–8775**. The repair test injects the reserved **18300–18349** range before calling the unchanged production handler, so its loopback control-plane evidence is valid but it is not proof that a stock launch honors the reserved-port policy.
- No configured remote host or SSH server was available. Remote execution remains `ENVIRONMENT_BLOCKED`; the controlled transport test validates command construction and fail-closed multi-tab behavior only.
- No macOS runner was available. macOS desktop packaging/runtime remains `NOT_TESTED`; Windows does not stand in for macOS.
- No authenticated provider run was authorized. GUI submission is verified through real intake and its generated contract artifact, but an AI-completed terminal run is not claimed.

## Entry-point trace

The GUI now carries `request_id` from `/intake` into the session URL and renders a `Session` / `Request` control-plane trace. The sprint contract remains the first user-visible generated artifact. A terminal `Done` state is only shown when the production projection reports a terminal status; it is never synthesized by the UI.

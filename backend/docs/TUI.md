# TianShu Terminal Workbench (TUI)

`tianshu` is a terminal-native workbench for the TianShu harness. It runs
**embedded** over `TianShuClient` — no Gateway, frontend, nginx, or Docker
services required — while honoring the same `config.yaml`, checkpointer, skills,
memory, MCP, and sandbox settings as the rest of TianShu.

![TianShu TUI](../../docs/tui/tui-preview.svg)

## Install & run

The TUI ships as an optional extra so the core harness install stays lean:

```bash
uv pip install 'tianshu-harness[tui]'    # or: pip install textual
```

Launch modes:

| Command | Behavior |
|---|---|
| `tianshu` | Launch the TUI when stdin/stdout are TTYs |
| `tianshu --tui` | Force the TUI (clear diagnostic if `textual` is missing) |
| `tianshu --cli` | Force headless/classic mode for one invocation |
| `tianshu chat` | Same TUI conversation surface |
| `tianshu --continue` | Resume the most recent thread |
| `tianshu --resume THREAD` | Resume a thread by id |
| `tianshu --print "question"` | Headless one-shot answer to stdout |
| `tianshu --json "question"` | Headless newline-delimited `StreamEvent`s |
| `tianshu --recursion-limit 250 --print "question"` | Set the headless agent-loop super-step limit |
| `echo "q" \| tianshu --print` | Read the message from stdin |
| `TIAN_SHU_TUI=1 tianshu` | Force the TUI via environment |

If no TTY is available and no headless flag is given, `tianshu` prints guidance
instead of hanging.

Headless runs use a recursion limit of `100` by default. Pass a positive
`--recursion-limit` when a longer agent loop is expected. This is a LangGraph
super-step budget, so it can include model and tool-execution steps rather than
mapping one-to-one to conversational turns. The `max_recursion_limit` setting
is a Gateway safety ceiling for client-supplied values; it is not the default
for trusted embedded CLI runs.

## Surface

- **Header** — model, thread, project root, skill/tool counts.
- **Transcript** — user prompts, assistant answers, and compact tool cards
  (`⚙ Read path ✓`) with dimmed result previews. Finalized assistant messages
  render as Markdown (headings, bold, lists, code, links); the actively-streaming
  message stays plain text to avoid reflow jumpiness and snaps to Markdown when
  it completes. Transcript re-renders are coalesced (~16 fps) so streaming stays
  smooth on long threads.
- **Status line** — run state + animated spinner, model, thread title, token
  usage, and an `esc interrupt` hint while a run is active.
- **Composer** — rounded input box. `/` opens the command palette.

### Keys

| Key | Action |
|---|---|
| `Enter` | Send message / accept palette selection |
| `/` | Open the slash-command palette |
| `↑` / `↓` | Palette navigation, or input history when the palette is closed |
| `Tab` | Complete the highlighted command (adds a trailing space) |
| `Esc` | Close the palette / overlay |
| `Ctrl+C` | Interrupt the active run, or quit when idle |
| `Ctrl+L` | Redraw · `Ctrl+U` clear composer |

### Slash commands

`/help` `/new` `/clear` `/goal` `/threads` (`/switch`) `/model` `/skills` `/tools`
`/mcp` `/memory` `/uploads` `/usage` `/config` `/quit`, plus
`/<skill-name> task` to activate any enabled skill for the current turn (same
semantics as elsewhere in TianShu). `/model` and `/threads` open modal pickers.

`/clear` removes the current transcript rows from the terminal display only; it keeps the active thread and persisted conversation intact. During an active run, `/new` and `/clear` ask you to wait for the run to finish instead of resetting in-flight display state.
Use `/goal <condition>` to set the active thread goal, `/goal` to show it, and
`/goal clear` to clear it.

## Architecture

The TUI is a UI shell over the existing embedded harness — it does **not** fork
agent behavior.

```
cli.py          launch-mode planning (pure) + headless print/json + entry point
session.py      builds TianShuClient (+ checkpointer) and the persistence writer
runtime.py      StreamEvent  ->  reducer actions  (pure translate + threaded driver)
view_state.py   ViewState + reduce(state, action)  (pure, the testable heart)
message_format  compact tool summaries / truncation (pure)
command_registry slash-command registry + resolve (pure)
input_history   bounded ↑/↓ history (pure)
render.py       Rich renderers for header / transcript / status / palette (pure)
theme.py        palette + symbols
app.py          Textual App: composes widgets, drives runs on a worker thread,
                marshals actions back to the UI thread, renders ViewState
persistence.py  writes threads_meta so sessions appear in the Web UI (below)
```

`TianShuClient.stream()` is a **synchronous** generator, so the app runs it on a
Textual worker *thread* and marshals each yielded action back to the UI thread
via `call_from_thread`. The pure layers (everything except `app.py`) have no
Textual dependency and are unit-tested directly with synthetic `StreamEvent`s.

## Web UI visibility (shared persistence)

The Web UI lists conversations from the `threads_meta` SQL table (filtered by
`user_id`), **not** from the checkpointer. An embedded run only writes the
checkpointer, so a TUI thread would otherwise be invisible in the sidebar.

`persistence.py` closes that gap: on the first turn of a thread it writes a
`threads_meta` row — owned by the local default user (`"default"`) — into the
**same** database the Gateway reads, and syncs the generated title afterward.
This requires only the shared `threads_meta` store (built via
`tianshu.persistence.engine.init_engine_from_config`), **not** the Gateway
process. When the database backend is `memory` (no SQL store) the writer
degrades to a silent no-op and the TUI still works.

All DB work runs on one long-lived background event loop, because a SQLAlchemy
async engine is bound to the loop that created it.

## Tests

Pure layers are TDD'd in `backend/tests/test_tui_*.py`; the Textual app, slash
palette, and modal overlays are exercised through Textual's pilot harness with a
fake in-process session (no live model). `test_tui_persistence.py` proves the
`threads_meta` write/read round-trip.

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k tui -q
```

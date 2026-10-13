"""M26 local debug logging — the only module that configures logging.

Turned on by `server.py --debug [--debug-payloads]` (also
`tools/start-server.bat --debug`). Design: specs/14-observability.md
§Local debug mode. Everything is local console output on **stderr** — no
network, no key, no export: M17's §Scope boundary ("server.py never
traces, LangSmith unreachable") holds unchanged, and this module must
never import `langsmith` or any network client (asserted by m26_check).
Writing to stderr keeps normal-mode stdout byte-stable even in debug mode.

Line format: ``<level> <time> [run-id] <message>`` where run-id is the
run's LangGraph ``thread_id`` (also surfaced in ``/api/status``). Off by
default: every hook below is a one-boolean no-op and the console output
is exactly what it was before M26.

Hooks (thin call sites live elsewhere):
- `dbg(kind, msg)` — one event line (run/request/intake/gate lifecycle)
- `err(msg)` — ERROR line + the current exception's traceback
- `stage(name)` decorator — graph-node enter/exit + ms + update summary
- `llm_call(...)` — one summary per `llm.chat()` call; prompt/response
  bodies (resume/JD text — PII) only under `--debug-payloads`
"""

from __future__ import annotations

import functools
import logging
import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar

LOGGER_NAME = "skill_gap_agent.debug"

_enabled = False
_payloads = False
_run_id: str | None = None

_log = logging.getLogger(LOGGER_NAME)
# One console handler, never doubled via the root logger: no other module
# configures logging (decision rows M26, specs/02-decisions.md).
_log.propagate = False


class _Formatter(logging.Formatter):
    """`<level> <time> [run-id] <message>` — lowercase level, HH:MM:SS."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        line = f"{record.levelname.lower()} {stamp} [{_run_id or '-'}] "
        line += record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            line += "\n" + self.formatException(record.exc_info)
        return line


_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_Formatter())
_log.addHandler(_handler)
_log.setLevel(logging.CRITICAL + 1)  # off until configure()


def configure(debug: bool = False, payloads: bool = False) -> None:
    """Turn the channel on/off. `--debug-payloads` implies `--debug`."""
    global _enabled, _payloads
    _payloads = bool(payloads)
    _enabled = bool(debug or payloads)
    _log.setLevel(logging.DEBUG if _enabled else logging.CRITICAL + 1)


def enabled() -> bool:
    return _enabled


def payloads_enabled() -> bool:
    return _payloads


def set_run_id(run_id: str | None) -> None:
    """Bind subsequent lines to a run (the LangGraph thread_id)."""
    global _run_id
    _run_id = run_id


def run_id() -> str | None:
    return _run_id


def dbg(kind: str, msg: str) -> None:
    """One event line: `dbg("run", "start ...")` -> `info ... [id] run: start ...`."""
    if not _enabled:
        return
    _log.info("%s: %s", kind, msg)


def err(msg: str) -> None:
    """ERROR line + the current exception's traceback (call inside except)."""
    if not _enabled:
        return
    _log.error("%s", msg, exc_info=True)


def _counts(update: Any) -> str:
    """Compact counts summary of a node's state update — metadata only."""
    if not isinstance(update, dict):
        return "-"
    parts = []
    for key, val in update.items():
        if isinstance(val, (list, tuple, set)):
            parts.append(f"{key}={len(val)}")
        elif isinstance(val, dict):
            if len(val) <= 4:
                inner = ",".join(
                    f"{k}={len(v) if isinstance(v, (list, dict)) else v}"
                    for k, v in val.items()
                )
            else:
                inner = f"{len(val)} keys"
            parts.append(f"{key}={{{inner}}}")
        else:
            parts.append(f"{key}={val}")
    return "[" + " ".join(parts) + "]"


_F = TypeVar("_F", bound=Callable[..., Any])


def stage(name: str) -> Callable[[_F], _F]:
    """Graph-node enter/exit wrapper: ms + counts of the returned update."""

    def deco(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _enabled:
                return fn(*args, **kwargs)
            dbg("stage", f"{name} enter")
            started = time.perf_counter()
            try:
                out = fn(*args, **kwargs)
            except Exception as e:
                ms = (time.perf_counter() - started) * 1000.0
                # A LangGraph interrupt() is a pause, not a failure (the
                # node re-executes on resume). Name check keeps this module
                # stdlib-only — langgraph is not imported here.
                if type(e).__name__ in ("GraphInterrupt", "GraphBubbleUp"):
                    dbg("stage", f"{name} interrupt in {ms:.1f}ms")
                else:
                    dbg("stage", f"{name} fail in {ms:.1f}ms error={type(e).__name__}: {e}")
                raise
            ms = (time.perf_counter() - started) * 1000.0
            dbg("stage", f"{name} exit in {ms:.1f}ms out={_counts(out)}")
            return out

        return wrapper  # type: ignore[return-value]

    return deco


def _usage(usage: Any) -> tuple[Any, Any]:
    if usage is None:
        return "-", "-"
    if isinstance(usage, dict):
        return usage.get("prompt_tokens", "-"), usage.get("completion_tokens", "-")
    return (
        getattr(usage, "prompt_tokens", "-"),
        getattr(usage, "completion_tokens", "-"),
    )


def llm_call(
    *,
    provider: str,
    model: str | None,
    ms: float,
    attempts: int,
    rotations: int = 0,
    usage: Any = None,
    error: str | None = None,
    prompt: str | None = None,
    system: str = "",
    response: str | None = None,
) -> None:
    """One summary line per `llm.chat()` call (the single call-summary hook).

    Bodies print only under `--debug-payloads` — prompts and responses
    carry resume/JD text (PII).
    """
    if not _enabled:
        return
    tok_in, tok_out = _usage(usage)
    dbg(
        "llm",
        f"{provider}/{model or '-'} in {ms:.0f}ms attempts={attempts} "
        f"rotations={rotations} tok={tok_in}/{tok_out} "
        + (f"error={error}" if error else "ok=1"),
    )
    if _payloads:
        if system:
            _log.info("llm system: %s", system)
        if prompt:
            _log.info("llm prompt: %s", prompt)
        if response:
            _log.info("llm response: %s", response)

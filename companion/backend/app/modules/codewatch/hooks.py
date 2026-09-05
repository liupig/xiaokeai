"""可选：往 ~/.cursor/hooks.json 装一条转发钩子，开工/收工更准。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from .service import bus

HOOK_EVENTS = (
    "sessionStart",
    "beforeSubmitPrompt",
    "preToolUse",
    "stop",
    "sessionEnd",
)

HOOK_MARK = "xiaoke-codewatch"
STARTED_EVENTS = {
    "sessionstart", "session_start",
    "beforesubmitprompt", "before_submit_prompt",
    "userpromptsubmit", "user_prompt_submit",
}
WORKING_EVENTS = {
    "pretooluse", "pre_tool_use",
    "posttooluse", "post_tool_use",
    "afteragentthought", "after_agent_thought",
    "afteragentresponse", "after_agent_response",
    "subagentstart", "subagent_start",
}
DONE_EVENTS = {
    "stop", "sessionend", "session_end",
    "subagentstop", "subagent_stop",
}


def cursor_dir() -> Path:
    return Path.home() / ".cursor"


def hooks_json_path() -> Path:
    return cursor_dir() / "hooks.json"


def hook_script_path() -> Path:
    return cursor_dir() / "hooks" / "xiaoke-codewatch.ps1"


def hint_path() -> Path:
    return cursor_dir() / "xiaoke-codewatch.json"


def bundled_script() -> Path:
    return Path(__file__).with_name("hook.ps1")


def write_hint(ports: List[int]) -> None:
    path = hint_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"ports": ports}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def status() -> Dict[str, Any]:
    script = hook_script_path()
    cfg = hooks_json_path()
    installed = script.is_file() and cfg.is_file() and HOOK_MARK in _read_text(cfg)
    return {
        "installed": installed,
        "hooks_json": str(cfg) if cfg.is_file() else "",
        "script": str(script) if script.is_file() else "",
    }


def install(ports: List[int]) -> Dict[str, Any]:
    src = bundled_script()
    if not src.is_file():
        raise RuntimeError("hook script missing")
    dest = hook_script_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    write_hint(ports)
    cfg_path = hooks_json_path()
    data = _load_hooks(cfg_path)
    hooks = data.setdefault("hooks", {})
    cmd = (
        "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass "
        "-File ./hooks/xiaoke-codewatch.ps1"
    )
    for event in HOOK_EVENTS:
        rows = hooks.get(event)
        if not isinstance(rows, list):
            rows = []
            hooks[event] = rows
        if any(HOOK_MARK in str((row or {}).get("command") or "") for row in rows if isinstance(row, dict)):
            continue
        rows.append({"command": cmd, "timeout": 4})
    if "version" not in data:
        data["version"] = 1
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status()


def uninstall() -> Dict[str, Any]:
    cfg_path = hooks_json_path()
    if cfg_path.is_file():
        data = _load_hooks(cfg_path)
        hooks = data.get("hooks") or {}
        changed = False
        for event, rows in list(hooks.items()):
            if not isinstance(rows, list):
                continue
            keep = [
                row for row in rows
                if not (isinstance(row, dict) and HOOK_MARK in str(row.get("command") or ""))
            ]
            if len(keep) != len(rows):
                hooks[event] = keep
                changed = True
            if not hooks[event]:
                hooks.pop(event, None)
                changed = True
        if changed:
            if hooks:
                data["hooks"] = hooks
                cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                # 只剩空壳且原本可能是我们建的：留下 version，别删用户文件。
                data["hooks"] = {}
                cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = hook_script_path()
    if script.is_file():
        try:
            script.unlink()
        except OSError:
            pass
    hint = hint_path()
    if hint.is_file():
        try:
            hint.unlink()
        except OSError:
            pass
    return status()


def ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = _event_name(payload)
    key = _norm(event)
    raw_src = str(payload.get("source") or payload.get("client") or "").lower()
    source = "cursor"
    if raw_src in ("codex", "cc", "lingma", "trae", "comate", "cursor"):
        source = raw_src
    elif "claude" in raw_src:
        source = "cc"
    elif "lingma" in raw_src or "tongyi" in raw_src:
        source = "lingma"
    elif "trae" in raw_src:
        source = "trae"
    elif "comate" in raw_src or "文心" in raw_src:
        source = "comate"
    title = _clip_title(payload)
    project = _project(payload)
    tool = str(payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or "")
    if key in STARTED_EVENTS:
        snap = bus.note("started", source=source, title=title, project=project, hint="新活来了")
    elif key in DONE_EVENTS:
        snap = bus.note("done", source=source, title=title, project=project, hint="这轮完了")
    elif key in WORKING_EVENTS or key:
        snap = bus.note("working", source=source, title=title, project=project, tool=tool)
    else:
        snap = None
    return {"ok": True, "event": event, "applied": snap is not None}


def _event_name(payload: Dict[str, Any]) -> str:
    for key in ("hook_event_name", "hookEventName", "event_name", "eventName", "event"):
        val = payload.get(key)
        if val:
            return str(val)
    return ""


def _project(payload: Dict[str, Any]) -> str:
    roots = payload.get("workspace_roots") or payload.get("workspaceRoots") or []
    if isinstance(roots, list) and roots:
        try:
            return Path(str(roots[0])).name
        except Exception:
            return str(roots[0])[-48:]
    return str(payload.get("cwd") or payload.get("workspace") or "")[-48:]


def _clip_title(payload: Dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "text", "query"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return " ".join(val.split())
    return ""


def _norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _load_hooks(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "hooks": {}}
    try:
        data = json.loads(_read_text(path) or "{}")
    except json.JSONDecodeError:
        return {"version": 1, "hooks": {}}
    return data if isinstance(data, dict) else {"version": 1, "hooks": {}}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""

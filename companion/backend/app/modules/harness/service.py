"""长驻 dsh。一个进程，一条角色一条会话，技能放在隔离的 home 里。"""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence

from ...paths import DATA_DIR
from ...services.llm import TagStreamParser
from ...services.settings_store import apply_llm_overlay
from .brief import SpokenGate, TextGrowth, turn_text

SKILL_SRC = Path(__file__).resolve().parent / "skills"
_LOCK = threading.Lock()
_RUNTIME: Optional["Runtime"] = None


class HarnessError(RuntimeError):
    pass


def _turn_error(events: Any) -> str:
    if not isinstance(events, list):
        return "dsh 这一轮失败"
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("type") != "turn/end":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        reason = data.get("reason") if isinstance(data.get("reason"), dict) else {}
        err = reason.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or err.get("code") or "").strip()
            if message:
                return message.splitlines()[0][:240]
        if isinstance(err, str) and err.strip():
            return err.strip().splitlines()[0][:240]
    return "dsh 这一轮失败"


def home_dir() -> Path:
    return DATA_DIR / "dsh"


def workspace_dir() -> Path:
    return home_dir() / "workspace"


def process_cwd(workspace: Path) -> str | None:
    """Windows 上进程目录不在 C: 或 V: 时，快照里的 koffi 会加载失败。

    会话工作目录仍用 workspace。这里只改子进程自己的 cwd。
    """
    if os.name != "nt":
        return None
    drive = workspace.resolve().drive.upper()
    if drive in {"C:", "V:"}:
        return None
    candidates = [
        os.environ.get("LOCALAPPDATA") or "",
        tempfile.gettempdir(),
        os.environ.get("SYSTEMROOT") or "",
    ]
    for raw in candidates:
        if not raw:
            continue
        base = Path(raw)
        if base.drive.upper() not in {"C:", "V:"}:
            continue
        folder = base / "xiaokeai-dsh"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(folder)
    return None


ENDPOINT_HINT = (
    "豆包角色模型不能走 harness 的 Messages 接口。"
    "请在模型一栏填入方舟推理接入点（ep- 开头），不要填模型名。"
)


def harness_llm(llm: Dict[str, Any] | None) -> Dict[str, Any]:
    """技能目录用自己的模型。地址和钥匙空着就跟对话模型。

    对话钥匙来自环境变量时，先补上钥匙，再把模型换回技能目录那一个。
    """
    src = dict(llm or {})
    model = str(src.get("harness_model") or "").strip()
    if not model:
        return src
    from ...services.settings_store import apply_llm_overlay

    out = dict(apply_llm_overlay(src))
    out["model"] = model
    base = str(src.get("harness_base_url") or "").strip()
    if base:
        out["base_url"] = base
    key = str(src.get("harness_api_key") or "").strip()
    if key:
        out["api_key"] = key
    return out


def turn_uses_harness(
    *,
    enabled: bool,
    mode: str,
    model: str | None,
    base_url: str | None,
    reroll: bool = False,
    afterglow: bool = False,
) -> bool:
    """角色模型名没有 Messages 权限，这一轮留在原来的对话接口。填了 ep- 才进 dsh。"""
    from .brief import wants_harness

    if not wants_harness(enabled=enabled, mode=mode, reroll=reroll, afterglow=afterglow):
        return False
    if not character_model_needs_endpoint(model, base_url):
        return True
    global _CHARACTER_BYPASS_NOTED
    if not _CHARACTER_BYPASS_NOTED:
        _CHARACTER_BYPASS_NOTED = True
        print("[harness] 豆包角色模型走原来的对话接口，不进 dsh")
    return False


_CHARACTER_BYPASS_NOTED = False


def character_model_needs_endpoint(model: str | None, base_url: str | None) -> bool:
    """角色模型名没有 Messages 权限。接入点 id（ep-）可以，模型名不行。"""
    name = (model or "").strip()
    if not name or name.lower().startswith("ep-"):
        return False
    if "character" not in name.lower():
        return False
    raw = (base_url or "").strip()
    if not raw:
        return True
    host = (urlsplit(raw).hostname or "").lower()
    if not host:
        return True
    return host.endswith("volces.com") or host.endswith("volcengine.com")


def messages_base(base_url: str | None) -> str | None:
    """dsh 官方适配器走 Anthropic Messages，钥匙放在 x-api-key。

    设置里存的是 OpenAI 兼容地址。方舟的 /api/v3 不认这把钥匙的这种放法，
    同一把钥匙要打到 Messages 口：/api/v3 → /api/compatible，
    /api/coding/v3 和 /api/plan/v3 去掉末尾的 /v3。
    """
    if not base_url:
        return None
    raw = base_url.strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return raw.rstrip("/")
    path = parsed.path.rstrip("/")
    host = (parsed.hostname or "").lower()
    if host.endswith("volces.com") or host.endswith("volcengine.com"):
        if path.endswith("/v3"):
            parent = path[: -len("/v3")]
            path = "/api/compatible" if parent in {"", "/api"} else parent
    elif host == "api.deepseek.com" and path in {"", "/v1"}:
        path = "/anthropic"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def glance_on() -> bool:
    """看一眼默认关。读不到设置就当关着，避免把眼睛写进本来的对话。"""
    try:
        from sqlmodel import Session

        from ...db import engine
        from ...services.settings_store import get_all

        with Session(engine) as session:
            mods = get_all(session).get("modules") or {}
        return bool(mods.get("glance", False))
    except Exception:
        return False


def sync_skills(home: Optional[Path] = None, *, glance: bool = False) -> Path:
    """把仓库里的技能抄到这次运行的 home。正文变了就覆盖，别的文件不动。

    glance 关着时不抄 watch，并把上次留下的那份删掉。
    """
    root = home or home_dir()
    dest_root = root / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    _write_profile_patch(root, glance=glance)
    if not SKILL_SRC.is_dir():
        return root
    for skill in SKILL_SRC.glob("*/SKILL.md"):
        if skill.parent.name == "watch" and not glance:
            continue
        target = dest_root / skill.parent.name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = skill.read_text(encoding="utf-8")
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
    if not glance:
        stale = dest_root / "watch" / "SKILL.md"
        if stale.is_file():
            stale.unlink()
    return root


def _skill_body(name: str) -> str:
    """正文进系统提示。目录里这条就不再让模型先加载再开口。"""
    text = (SKILL_SRC / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            text = text[end + 4 :]
    return text.replace("\r\n", "\n").strip("\n")


def _inline_rules() -> str:
    parts = [_skill_body(name) for name in ("chat", "tarot", "draw")]
    return "\n\n".join(part for part in parts if part)


def _profile_patch(*, glance: bool = False) -> str:
    # 自动折叠在开口前同步写摘要，摘要模板还是编程纪要。满了改由宿主换一条短会话。
    rules = "\n".join(
        f"      {line}" if line else "" for line in _inline_rules().split("\n")
    )
    eyes = ""
    if glance:
        eyes = "对方问自己在干什么、让你陪着看剧或看视频、或让你在屏幕上找东西在哪时，调用 watch 技能。先说「我看看。」再只写 [glance:对方的要求]。宿主去看屏幕。这一轮不要编，不要去点。"
    return (
        "- id: compaction-basic\n"
        "  config:\n"
        "    auto: false\n"
        "- id: tool-web\n"
        "  config:\n"
        "    search: false\n"
        "    fetch: false\n"
        "- id: system-prompt\n"
        "  config:\n"
        "    personaPrefix: |\n"
        "      系统提醒、技能名单、技能名字和你自己的推理，一个字都不要说出来。对方听得见的只有口语。\n"
        "      闲聊、看牌、画画、魅影酒馆直接开口，不要为它们调用 skill。对方要去魅影酒馆时，牌桌已经由宿主打开，用一两句邀对方选牌组再入座，不要宣布已经发牌。对方要跳舞时，铺垫已经说了，接着调用 dance 技能，回来后再说一句并写 [dance:]。对方要核对现在的事时，调用 lookup 技能，检索词由你自己改写，只写 [lookup:检索词]。宿主按原词去查。不要自己打开搜索网站，不要编。"
        f"{eyes}不要把技能说出来。\n"
        f"{rules}\n"
    )


def _write_profile_patch(root: Path, *, glance: bool = False) -> None:
    dest = root / "profiles" / "sdk" / "cordis.patch.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = _profile_patch(glance=glance)
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8")


def sdk_installed() -> bool:
    try:
        import deepseek_harness  # noqa: F401
    except ImportError:
        return False
    return True


def _seed_path(character_id: int) -> Path:
    return home_dir() / "xiaoke-seed" / str(int(character_id))


def needs_seed(character_id: int) -> bool:
    return not _seed_path(character_id).is_file()


def mark_seed(character_id: int) -> None:
    path = _seed_path(character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1", encoding="utf-8")


def session_label(character_id: int, generation: int) -> str:
    base = f"xiaoke-{int(character_id)}"
    return base if int(generation) <= 0 else f"{base}-{int(generation)}"


def _generation_path(character_id: int) -> Path:
    return home_dir() / "xiaoke-seed" / f"{int(character_id)}.gen"


def _generation(character_id: int) -> int:
    try:
        return int(_generation_path(character_id).read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


# 这条会话第 53 句开始折，折完仍贴着触发线，后面几乎一句一折。36 句时先换掉。
CUT_AFTER_TURNS = 36


def _turns_path(character_id: int) -> Path:
    return home_dir() / "xiaoke-seed" / f"{int(character_id)}.turns"


def _read_turns(character_id: int) -> int | None:
    path = _turns_path(character_id)
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _write_turns(character_id: int, count: int) -> None:
    path = _turns_path(character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(count)), encoding="utf-8")


def should_cut(*, turns: int | None, generation: int, seeded: bool) -> bool:
    """长会话在下一句之前换掉。已经叠满、还没开始计数的旧会话也换。"""
    if turns is None:
        return bool(seeded) and int(generation) > 0
    return int(turns) >= CUT_AFTER_TURNS


def cut_session(character_id: int) -> int:
    """换一条新会话。下一句会带上最近十轮，不再接着旧摘要。"""
    generation = _generation(character_id) + 1
    path = _generation_path(character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(generation), encoding="utf-8")
    seed = _seed_path(character_id)
    if seed.is_file():
        seed.unlink()
    _write_turns(character_id, 0)
    return generation


def note_kept_turn(character_id: int) -> None:
    count = _read_turns(character_id) or 0
    _write_turns(character_id, count + 1)


def _event_of(notification: Any) -> Optional[Dict[str, Any]]:
    method = getattr(notification, "method", None)
    payload = getattr(notification, "payload", None)
    if method is None and isinstance(notification, dict):
        method = notification.get("method")
        payload = notification.get("payload") or notification.get("params")
    if method != "session.event" or not isinstance(payload, dict):
        return None
    event = payload.get("event")
    return event if isinstance(event, dict) else None


def reasoning_effort_for(thinking: str | None) -> str | None:
    """设置里的思考开关。dsh 不传时自己默认 high，闲聊会先写一大段再开口。"""
    value = (thinking or "default").strip()
    if value == "off":
        return "off"
    if value == "on":
        return "high"
    return None


def turn_max_tokens(base_url: str | None, max_tokens: int, thinking: str | None) -> int | None:
    """没填上限时不要按接口天花板去要。dsh 空白会带 256000，方舟超过 131072 直接 400。"""
    asked = int(max_tokens or 0)
    host = (base_url or "").lower()
    volc = "volces.com" in host or "volcengine.com" in host
    if asked <= 0:
        if not volc:
            return None
        return 8192 if (thinking or "").strip() == "on" else 2048
    if volc and asked > 131072:
        return 131072
    return asked


def session_missing(exc: BaseException) -> bool:
    text = str(exc)
    return " not found" in text or "does not exist" in text


# 管道断了就是子进程没了。名字对上就丢掉，下一句重新拉起。
_DEAD_EXC = frozenset({
    "TransportClosedError",
    "BrokenPipeError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "EOFError",
})


class Runtime:
    def __init__(self) -> None:
        self._harness = None
        self._launch: tuple | None = None
        self._turn = threading.Lock()
        self._open_ids: set[str] = set()

    def close(self) -> None:
        with self._turn:
            harness = self._harness
            self._harness = None
            self._launch = None
            self._open_ids.clear()
        if harness is not None:
            try:
                harness.close()
            except Exception as exc:
                print(f"[harness] close failed: {exc}")

    def running(self) -> bool:
        return self._harness is not None

    def _child_alive(self) -> bool:
        harness = self._harness
        if harness is None:
            return False
        client = getattr(harness, "client", None)
        if client is None:
            client = getattr(harness, "_client", None)
        proc = getattr(client, "_proc", None) if client is not None else None
        if proc is None:
            return not bool(getattr(harness, "_initialized", False))
        poll = getattr(proc, "poll", None)
        if poll is None:
            return True
        try:
            return poll() is None
        except Exception:
            return False

    def _take_if_dead(self, exc: BaseException | None = None):
        """调用方持着锁。进程已经退出时取出旧对象，交给外面关掉。"""
        if self._harness is None:
            return None
        crashed = exc is not None and type(exc).__name__ in _DEAD_EXC
        if not crashed and self._child_alive():
            return None
        harness = self._harness
        self._harness = None
        self._launch = None
        self._open_ids.clear()
        return harness

    def retire_if_dead(self, exc: BaseException | None = None) -> None:
        with self._turn:
            stale = self._take_if_dead(exc)
        if stale is None:
            return
        print("[harness] runtime exited, next turn starts a new one")
        try:
            stale.close()
        except Exception as close_exc:
            print(f"[harness] close failed: {close_exc}")

    def ensure(self, llm_conf: Dict[str, Any]):
        with self._turn:
            stale = self._take_if_dead()
            if stale is not None:
                print("[harness] runtime exited, starting again")
                try:
                    stale.close()
                except Exception as exc:
                    print(f"[harness] close failed: {exc}")
            conf = apply_llm_overlay(llm_conf)
            api_key = (conf.get("api_key") or "").strip()
            model = (conf.get("model") or "").strip() or "deepseek-v4-flash"
            raw_base = (conf.get("base_url") or "").strip()
            if character_model_needs_endpoint(model, raw_base):
                raise HarnessError(ENDPOINT_HINT)
            base_url = messages_base(raw_base or None)
            effort = reasoning_effort_for(conf.get("thinking"))
            cap = turn_max_tokens(base_url, int(conf.get("max_tokens") or 0), conf.get("thinking"))
            launch = (model, base_url, effort, cap)
            if self._harness is not None and self._launch == launch:
                return self._harness
            if not api_key:
                if self._harness is not None:
                    return self._harness
                raise HarnessError("未配置 LLM API Key，请到设置中填写")
            if self._harness is not None:
                print("[harness] model settings changed, starting again")
                old = self._harness
                self._harness = None
                self._launch = None
                self._open_ids.clear()
                try:
                    old.close()
                except Exception as exc:
                    print(f"[harness] close failed: {exc}")
            if not sdk_installed():
                raise HarnessError("内置的 dsh 运行时没有装进当前环境")
            from deepseek_harness import DeepSeekHarness

            home = sync_skills(glance=glance_on())
            workspace = workspace_dir()
            launched_at = process_cwd(workspace)
            self._harness = DeepSeekHarness(
                dsh_home=str(home),
                cwd=str(workspace),
                runtime_cwd=launched_at,
                profile="sdk",
                provider="deepseek-official",
                model=model,
                reasoning_effort=effort,
                base_url=base_url,
                api_key=api_key,
                initialize_timeout_seconds=120.0,
                max_tokens=cap,
            )
            self._launch = launch
            return self._harness

    def _ensure_open(self, harness, session_id: str) -> None:
        """磁盘上已有这条会话时先恢复。prompt 只会新建，撞上旧文件就报 already exists。"""
        if session_id in self._open_ids:
            return
        try:
            harness.resume_session(session_id)
        except Exception as exc:
            if session_missing(exc):
                return
            raise
        self._open_ids.add(session_id)

    def run_turn(
        self,
        llm_conf: Dict[str, Any],
        *,
        character_id: int,
        user_text: str,
        brief: str,
        prior: Sequence[Dict[str, str]] | None,
        on_delta,
        recall: str = "",
    ) -> str:
        harness = self.ensure(llm_conf)
        if should_cut(
            turns=_read_turns(character_id),
            generation=_generation(character_id),
            seeded=not needs_seed(character_id),
        ):
            cut_session(character_id)
        session_id = session_label(character_id, _generation(character_id))
        seeded = not needs_seed(character_id)
        # 人设和舞蹈名单已经在会话里。每轮再贴一遍，短句也会越来越慢。
        # 看牌的现场会变，这一轮仍要带上。
        keep_brief = (not seeded) or ("【当前扮演】" in brief) or ("【这一轮任务】" in brief)
        prompt = turn_text(
            brief=brief if keep_brief else "",
            user_text=user_text,
            prior=None if seeded else prior,
            recall=recall,
        )
        growth = TextGrowth()

        def on_notification(notification: Any) -> None:
            event = _event_of(notification)
            if event is None:
                return
            delta = growth.feed(event)
            if delta:
                on_delta(delta)

        try:
            with self._turn:
                self._ensure_open(harness, session_id)
                try:
                    result = harness.start_session(session_id).run(
                        prompt,
                        on_notification=on_notification,
                    )
                except Exception as exc:
                    if session_id in self._open_ids or "already exists" not in str(exc):
                        raise
                    harness.resume_session(session_id)
                    self._open_ids.add(session_id)
                    result = harness.start_session(session_id).run(
                        prompt,
                        on_notification=on_notification,
                    )
                self._open_ids.add(session_id)
        except Exception as exc:
            self.retire_if_dead(exc)
            raise
        reason = getattr(result, "finish_reason", None)
        if reason == "error":
            raise HarnessError(_turn_error(getattr(result, "events", None)))
        final = growth.finish(getattr(result, "final_response", "") or "")
        if final:
            on_delta(final)
        if not seeded:
            mark_seed(character_id)
        note_kept_turn(character_id)
        return growth.emitted + final


def runtime() -> Runtime:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is None:
            _RUNTIME = Runtime()
        return _RUNTIME


def release() -> None:
    global _RUNTIME
    with _LOCK:
        current = _RUNTIME
        _RUNTIME = None
    if current is not None:
        current.close()


def status() -> Dict[str, Any]:
    current = _RUNTIME
    return {
        "installed": sdk_installed(),
        "running": bool(current and current.running()),
        "home": str(home_dir()),
    }


async def stream_reply(
    llm_conf: Dict[str, Any],
    *,
    character_id: int,
    user_text: str,
    brief: str,
    prior: Sequence[Dict[str, str]] | None = None,
    recall: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """把 dsh 的助手正文喂进现有标签解析，事件形状和 stream_chat 一致。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_delta(delta: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("delta", delta))

    def work() -> None:
        try:
            runtime().run_turn(
                llm_conf,
                character_id=character_id,
                user_text=user_text,
                brief=brief,
                prior=prior,
                on_delta=on_delta,
                recall=recall,
            )
        except Exception as exc:
            print(f"[harness] {exc}")
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("end", ""))

    threading.Thread(target=work, name="dsh-turn", daemon=True).start()
    parser = TagStreamParser()
    gate = SpokenGate()
    full_text = ""
    failed = False

    def _keep_text(delta: str) -> str:
        return gate.feed(delta)

    while True:
        kind, payload = await queue.get()
        if kind == "delta":
            for ev in parser.feed(payload):
                if ev.get("type") == "text":
                    spoken = _keep_text(ev.get("delta") or "")
                    if not spoken:
                        continue
                    ev = {"type": "text", "delta": spoken}
                    full_text += spoken
                yield ev
            continue
        if kind == "error":
            failed = True
            yield {"type": "error", "code": "harness", "message": payload}
            break
        break
    if not failed:
        for ev in parser.flush():
            if ev.get("type") == "text":
                spoken = _keep_text(ev.get("delta") or "")
                if not spoken:
                    continue
                ev = {"type": "text", "delta": spoken}
                full_text += spoken
            yield ev
        tail = gate.flush()
        if tail:
            full_text += tail
            yield {"type": "text", "delta": tail}
        yield {"type": "done", "full_text": full_text}

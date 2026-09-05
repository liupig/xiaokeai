"""LLM 网关：OpenAI 兼容接口代理，流式输出 + 情绪标签协议解析。

情绪标签协议：要求 LLM 在回复文本中内嵌形如 [emo:happy] [act:nod] [dance:xxx.vmd]
的标记。本模块在流式转发时把标记剥离为独立事件，纯文本作为 text 增量下发。
"""
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from .narration import STAGE_RE, map_stage_inner

TAG_RE = re.compile(r"\[(emo|act|dance|cam|expr|intent|stand):([^\[\]]{1,80})\]")

SYSTEM_PROTOCOL = """
你在扮演一个 3D 虚拟陪玩角色。文字会转成语音，表情和动作由工作室导演根据你的意图自动选角。
规则：
1. 用口语化中文回复，每句不要太长，像真人聊天。
2. 只输出高层表演标记（不要写动作文件名，跳舞除外）：
   - 情绪（每次回复开头必须有）：[emo:happy] [emo:angry] [emo:sad] [emo:relaxed] [emo:neutral]
     可带强度 0~1，如 [emo:happy:0.4] 浅笑、[emo:happy:1] 非常开心。
   - 镜头 / 动作 / 站位是一套，先定景别，再配表演：
     · 特写 [cam:close]：悄悄话、心动。表情为主，只配 [intent:nod] [intent:look] [intent:shake]
     · 1/4 [cam:bust]：思考、害羞。可 [intent:think] [intent:shy]
     · 1/2 [cam:half]：默认聊天。可以做很多动作：挥手 [intent:greet]、比心 [intent:heart]、
       卖萌 [intent:cute]、说话比划 [intent:talk]、俏皮 [intent:tease]，不要换站位
     · 3/4 [cam:threeQ]：鞠躬 [intent:bow]、更大的身体动作
     · 全身 [cam:full]：坐下、走路、跳舞、换站位 [stand:…]
     · 远景 [cam:long]：舞台、完整舞蹈
   - 意图：有情绪起伏时加上。打招呼挥手用 [intent:greet] 配半身即可，不必拉全身。
   - 站位：用户说靠左/靠右/回中间时用 [stand:left] [stand:center] [stand:right]
     （站台左右位置，不是景别）。给站位前切全身。
   - 跳舞：仅当用户明确要求时，用 [dance:文件名] 从下方舞蹈列表选一支。
     用户说再来、换一支、继续、跳别的时，必须换一个和上一支不同的文件名，禁止重复。
   - 镜头：只在「景别该变」时给一次 [cam:…]，当作建议交给导演，不要每句都给。
     聊天默认 half，亲密 close，跳舞 full。运镜交给导演，不要自己点 45 度 / 90 度。
     不要背口诀（不要固定半身、不要告别必须拉远）。
3. 不要使用 markdown、emoji、颜文字，只输出对话正文和标记。
   不要用括号写动作或内心 OS。错：「（歪头蹭了蹭）对呀」——括号会被念出来。
   对：「[emo:happy][intent:cute]对呀，就是憨憨。」
"""


# prompt 组装已移至 services/prompt_stack.py（固定层架，每轮重拼）。


class TagStreamParser:
    """流式标签解析：跨 chunk 缓冲，剥离 [xxx:yyy] 标记。"""

    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> List[Dict[str, str]]:
        self.buf += delta
        events: List[Dict[str, str]] = []
        while True:
            m_tag = TAG_RE.search(self.buf)
            m_st = STAGE_RE.search(self.buf)
            m = None
            kind = ""
            if m_tag and m_st:
                if m_tag.start() <= m_st.start():
                    m, kind = m_tag, "tag"
                else:
                    m, kind = m_st, "stage"
            elif m_tag:
                m, kind = m_tag, "tag"
            elif m_st:
                m, kind = m_st, "stage"
            if m:
                if m.start() > 0:
                    events.append({"type": "text", "delta": self.buf[: m.start()]})
                if kind == "tag":
                    events.append({"type": m.group(1), "value": m.group(2).strip()})
                else:
                    events.extend(map_stage_inner(m.group(1)))
                self.buf = self.buf[m.end():]
                continue
            last_open = max(
                self.buf.rfind("["),
                self.buf.rfind("（"),
                self.buf.rfind("("),
                self.buf.rfind("【"),
            )
            if last_open == -1:
                if self.buf:
                    events.append({"type": "text", "delta": self.buf})
                self.buf = ""
            else:
                head = self.buf[:last_open]
                if head:
                    events.append({"type": "text", "delta": head})
                self.buf = self.buf[last_open:]
                if len(self.buf) > 100:
                    events.append({"type": "text", "delta": self.buf})
                    self.buf = ""
            break
        return events

    def flush(self) -> List[Dict[str, str]]:
        if not self.buf:
            return []
        s = self.buf
        self.buf = ""
        if s.startswith("["):
            return [{"type": "text", "delta": s}]
        if s[:1] in ("（", "(", "【"):
            return map_stage_inner(s[1:].strip("）)】"))
        return [{"type": "text", "delta": s}]


def _conf(llm_conf: Dict[str, Any]) -> Dict[str, Any]:
    from .settings_store import apply_llm_overlay
    return apply_llm_overlay(llm_conf)


def build_payload(llm_conf: Dict[str, Any], messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """按设置组装请求体：采样参数 + 各服务商的思考开关方言。"""
    model = llm_conf.get("model") or "gpt-4o-mini"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": float(llm_conf.get("temperature", 0.85)),
        "top_p": float(llm_conf.get("top_p", 1.0)),
    }
    max_tokens = int(llm_conf.get("max_tokens") or 0)
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens

    # 思考开关：default 时什么都不传（跟随模型默认，兼容仅思考/不思考的模型）
    # 豆包角色模型不支持思考方言，传了会 400
    thinking = llm_conf.get("thinking") or "default"
    if thinking in ("on", "off") and "character" not in model.lower():
        enabled = thinking == "on"
        base_url = llm_conf.get("base_url") or ""
        if "dashscope.aliyuncs.com" in base_url:
            payload["enable_thinking"] = enabled          # 阿里云百炼
        elif "volces.com" in base_url or "bigmodel.cn" in base_url:
            # 火山方舟 / 智谱 GLM 共用 thinking.type 协议
            payload["thinking"] = {"type": "enabled" if enabled else "disabled"}
        elif enabled and "openai.com" in base_url:
            payload["reasoning_effort"] = "medium"        # OpenAI 推理系列
        # 其他服务商不传，避免不识别的参数导致 400
    return payload


async def test_connection(llm_conf: Dict[str, Any]) -> Dict[str, Any]:
    """用当前配置发一次最小对话，验证地址/Key/模型是否匹配。"""
    import time
    llm_conf = _conf(llm_conf)
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    if not llm_conf.get("api_key"):
        return {"ok": False, "message": "未填写 API Key"}
    payload = build_payload(llm_conf, [{"role": "user", "content": "回复两个字：你好"}])
    payload["stream"] = False
    # 思考模型的推理也计入 max_tokens，太小会导致空回复
    payload["max_tokens"] = max(int(llm_conf.get("max_tokens") or 0), 512)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10),
                                     trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {llm_conf.get('api_key')}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"网络错误：{exc}"}
    ms = int((time.time() - t0) * 1000)
    if resp.status_code != 200:
        return {"ok": False,
                "message": f"HTTP {resp.status_code}：{resp.text[:200]}"}
    try:
        msg = resp.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError):
        return {"ok": False, "message": f"响应格式异常：{resp.text[:200]}"}
    reply = (msg.get("content") or "").strip()
    thinking = "，模型输出了思考过程" if msg.get("reasoning_content") else ""
    return {"ok": True, "message": f"连接成功（{ms}ms）：{reply[:40]}{thinking}"}


async def stream_chat(llm_conf: Dict[str, Any], messages: List[Dict[str, str]]
                      ) -> AsyncGenerator[Dict[str, Any], None]:
    """向 OpenAI 兼容接口发起流式对话，产出结构化事件。"""
    llm_conf = _conf(llm_conf)
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    api_key = llm_conf.get("api_key") or ""
    if not api_key:
        yield {"type": "error", "code": "no_api_key",
               "message": "未配置 LLM API Key，请到设置中填写"}
        return

    parser = TagStreamParser()
    full_text = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15),
                                     trust_env=False) as client:
            async with client.stream(
                "POST", f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=build_payload(llm_conf, messages),
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    yield {"type": "error", "code": "llm_http",
                           "message": f"LLM 接口返回 {resp.status_code}: {body}"}
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if not delta:
                        continue
                    for ev in parser.feed(delta):
                        if ev["type"] == "text":
                            full_text += ev["delta"]
                        yield ev
    except httpx.HTTPError as exc:
        yield {"type": "error", "code": "llm_network", "message": f"LLM 网络错误: {exc}"}
        return

    for ev in parser.flush():
        if ev["type"] == "text":
            full_text += ev["delta"]
        yield ev
    yield {"type": "done", "full_text": full_text}


async def complete_json(llm_conf: Dict[str, Any], messages: List[Dict[str, str]],
                        max_tokens: int = 800, timeout: float = 60) -> Optional[Any]:
    """非流式 JSON 补全。失败返回 None。"""
    llm_conf = _conf(llm_conf)
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    api_key = llm_conf.get("api_key") or ""
    if not api_key or not base_url:
        return None
    payload = build_payload(llm_conf, messages)
    payload["stream"] = False
    payload["max_tokens"] = max(int(llm_conf.get("max_tokens") or 0), max_tokens)
    connect = min(10.0, max(2.0, timeout))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect),
                                     trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            return None
        raw = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None
    return _parse_json_blob(raw)


def _parse_json_blob(raw: str) -> Optional[Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


async def embed_texts(llm_conf: Dict[str, Any], texts: List[str]) -> Optional[List[List[float]]]:
    """OpenAI 兼容 embeddings。按常见模型名依次尝试。"""
    llm_conf = _conf(llm_conf)
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    api_key = llm_conf.get("api_key") or ""
    if not api_key or not base_url or not texts:
        return None
    models = [
        "text-embedding-v3",
        "text-embedding-v4",
        "text-embedding-3-small",
        "embedding-3",
    ]
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=8),
                                 trust_env=False) as client:
        for model in models:
            try:
                resp = await client.post(
                    f"{base_url}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "input": texts},
                )
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()["data"]
                data = sorted(data, key=lambda x: x.get("index", 0))
                return [row["embedding"] for row in data]
            except (KeyError, TypeError, ValueError):
                continue
    return None

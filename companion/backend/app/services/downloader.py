"""模之屋（aplaybox）下载器。

协议（从站点前端逆向确认）：
- 认证：Authorization: Bearer <JWT> + provider: users + language: cn
- 详情：POST /work/getWorkDetails {work_uuid, work_type_id(1=model,2=motion), user_uid, is_login}
- 规则：详情里 work_download_rules {like_status, collect_status, follow_length...}
- 满足规则：POST /work/likeWork|collectWork {work_uuid, work_type_id}；
            POST /user/followUser {target_user_uid}
- 下载：POST /work/downloadWorkNewV2
        {work_type_id, work_uuid, is_camera, download_password, ticket, randstr}
        → result.data = [{url, ...}]（OSS 签名地址，需带 Referer 下载）
- 注意：站点会按下载频率触发腾讯图形验证码（错误码 20272），
        无法无头绕过，此时提示用户稍后重试或浏览器下载后本地导入。
"""
import asyncio
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import httpx

from ..paths import TMP_DIR

API = "https://api.aplaybox.com/api/web/v1"
WEB = "https://www.aplaybox.com"
WORK_TYPE_IDS = {"model": 1, "motion": 2}

# 内存任务表：task_id -> 状态
TASKS: Dict[str, Dict[str, Any]] = {}


def parse_work_url(url: str) -> Optional[Dict[str, Any]]:
    """从详情页 URL 提取作品 uid 与类型。"""
    m = re.search(r"aplaybox\.com/details/(model|motion)/([A-Za-z0-9]+)", url)
    if not m:
        return None
    return {
        "work_type": m.group(1),
        "work_type_id": WORK_TYPE_IDS[m.group(1)],
        "uid": m.group(2),
    }


class AplayboxError(RuntimeError):
    pass


class AplayboxClient:
    def __init__(self, token: str = "") -> None:
        token = token.strip()
        if token and not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            "Referer": WEB + "/",
            "Origin": WEB,
            "Content-Type": "application/json;charset=utf-8",
            "language": "cn",
        }
        if token:
            headers["Authorization"] = token
            headers["provider"] = "users"
        self.has_token = bool(token)
        self.http = httpx.AsyncClient(headers=headers, timeout=60, trust_env=False)

    async def close(self) -> None:
        await self.http.aclose()

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await self.http.post(f"{API}{path}", json=payload)
        resp.raise_for_status()
        body = resp.json()
        return body.get("data") or {}

    async def search(self, keyword: str, work_type_id: int = 2,
                     page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """站内搜索。type: 1=模型 2=动作。返回 {total, items:[...]}"""
        data = await self._post("/work/search", {
            "is_login": 0, "user_uid": "", "download_type": 1,  # 1=允许下载
            "type": work_type_id, "keyword": keyword, "sort_by": 2,  # 2=最多下载
            "user_title_type_id": 0, "current_page": page,
            "per_page": per_page, "page_type": 2,
        })
        pager = ((data.get("result") or {}).get("data")) or {}
        items = [{
            "work_uuid": it.get("work_uuid"),
            "work_name": it.get("work_name"),
            "introduction": (it.get("introduction") or "")[:120],
            "cover": it.get("cover"),
            "author": it.get("nick_name"),
            "downloads": it.get("downloaded_count"),
            "work_type": "model" if work_type_id == 1 else "motion",
            "url": f"{WEB}/details/{'model' if work_type_id == 1 else 'motion'}/{it.get('work_uuid')}",
        } for it in (pager.get("data") or [])]
        return {"total": pager.get("total") or 0, "items": items}

    async def get_work_details(self, uid: str, work_type_id: int) -> Dict[str, Any]:
        data = await self._post("/work/getWorkDetails", {
            "work_uuid": uid, "work_type_id": work_type_id,
            "user_uid": "", "is_login": 0,
        })
        result = (data.get("result") or {}).get("data")
        if not result:
            raise AplayboxError(f"获取作品详情失败：{data.get('message', '未知错误')}")
        return result

    async def satisfy_rules(self, uid: str, work_type_id: int,
                            details: Dict[str, Any],
                            required: Optional[list] = None) -> None:
        """按作品下载规则自动点赞/收藏/关注（用配置的账号）。"""
        rules = details.get("work_download_rules") or {}
        req = " ".join(required or [])
        if rules.get("like_status") or "赞" in req:
            await self._post("/work/likeWork",
                             {"work_uuid": uid, "work_type_id": work_type_id})
        if rules.get("collect_status") or "收藏" in req:
            await self._post("/work/collectWork",
                             {"work_uuid": uid, "work_type_id": work_type_id})
        # 详情里 follow_length=0 时，下载接口仍可能要求「需关注作者」
        if details.get("user_uid") and (rules.get("follow_length") or "关注" in req):
            await self._post("/user/followUser",
                             {"target_user_uid": details["user_uid"]})
            await asyncio.sleep(0.4)

    async def get_download_files(self, uid: str, work_type_id: int) -> list:
        """请求签名下载地址；自动满足规则后重试一次。"""
        details: Optional[Dict[str, Any]] = None
        for attempt in range(2):
            data = await self._post("/work/downloadWorkNewV2", {
                "work_type_id": work_type_id, "work_uuid": uid,
                "is_camera": False, "download_password": "",
                "ticket": "", "randstr": "",
            })
            err_code = (data.get("error") or {}).get("code")
            result = data.get("result") or {}
            rules_required = result.get("work_download_rules_required") or []
            files = result.get("data")
            if files and isinstance(files, list):
                return files
            if err_code == 20272 or "图形验证" in str(data.get("message", "")):
                raise AplayboxError(
                    "模之屋触发了图形验证码（下载太频繁）。请过一会儿再试，"
                    "或在浏览器里下载后用「导入本地文件」导入。")
            if rules_required:
                if not self.has_token:
                    raise AplayboxError(
                        f"该作品要求「{'、'.join(rules_required)}」后才能下载。"
                        "请到设置 → 下载中配置模之屋登录 token。")
                if attempt == 0:
                    if details is None:
                        details = await self.get_work_details(uid, work_type_id)
                    await self.satisfy_rules(uid, work_type_id, details, rules_required)
                    continue
                raise AplayboxError(
                    f"自动满足下载规则失败，仍要求：{'、'.join(rules_required)}")
            raise AplayboxError(f"获取下载地址失败：{data.get('message', '未知错误')}")
        raise AplayboxError("获取下载地址失败")

    async def download_file(self, url: str, dest: Path,
                            task: Dict[str, Any]) -> None:
        async with self.http.stream("GET", url) as resp:
            resp.raise_for_status()
            task["total"] = int(resp.headers.get("content-length") or 0)
            done = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    f.write(chunk)
                    done += len(chunk)
                    task["downloaded"] = done


def _filename_from_url(url: str, fallback: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return name or fallback


async def run_download_task(task_id: str, url: str, token: str, on_complete) -> None:
    """后台任务：详情 → 满足规则 → 签名地址 → 下载 → 导入。"""
    task = TASKS[task_id]
    client = AplayboxClient(token)
    try:
        info = parse_work_url(url)
        if not info:
            raise AplayboxError("无法识别的模之屋链接，需要形如 aplaybox.com/details/motion/xxxx")

        task.update(status="fetching", message="获取作品信息…")
        details = await client.get_work_details(info["uid"], info["work_type_id"])
        work_name = details.get("work_name") or info["uid"]
        task["work_name"] = work_name

        task.update(message="获取下载地址…")
        files = await client.get_download_files(info["uid"], info["work_type_id"])

        file_url = files[0]["url"] if isinstance(files[0], dict) else str(files[0])
        origin_name = _filename_from_url(file_url, f"{info['uid']}.zip")
        suffix = Path(origin_name).suffix or ".zip"
        dest = TMP_DIR / f"dl_{task_id}{suffix}"
        task.update(status="downloading", message=f"下载 {origin_name}…",
                    filename=origin_name)
        await client.download_file(file_url, dest, task)

        task.update(status="importing", message="解压导入中…")
        created = await asyncio.to_thread(
            on_complete, dest, info, work_name)
        task.update(status="done", message=f"导入完成：{work_name}",
                    assets=[{"id": a.id, "kind": a.kind, "label": a.label}
                            for a in created])
        dest.unlink(missing_ok=True)
    except AplayboxError as exc:
        task.update(status="error", message=str(exc))
    except Exception as exc:  # noqa: BLE001 —— 任务失败原因原样反馈给前端
        task.update(status="error", message=f"{type(exc).__name__}: {str(exc)[:400]}")
    finally:
        await client.close()


def create_task(url: str) -> str:
    task_id = uuid.uuid4().hex[:12]
    TASKS[task_id] = {
        "id": task_id, "url": url, "status": "pending",
        "message": "等待开始", "downloaded": 0, "total": 0,
    }
    return task_id

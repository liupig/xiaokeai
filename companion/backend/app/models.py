"""SQLModel 数据模型：资产 / 角色 / 会话 / 设置。"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Asset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)  # model | motion | camera
    name: str = Field(index=True)  # 唯一键：模型目录名 或 vmd 文件名
    label: str = ""
    path: str = ""  # 相对 assets/ 的路径，如 models/qingxiao/model.pmx
    fmt: str = ""  # pmx | vrm | glb | vmd
    size: int = 0
    source: str = "local"  # local | aplaybox | seed
    source_url: str = ""
    meta: str = "{}"  # JSON：bgm/camera/category/表情vmd/配布规则等
    created_at: datetime = Field(default_factory=utc_now)


class Character(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    model_asset_id: int = 0
    persona: str = ""  # 人设 system prompt
    boundary: str = "free"  # 聊天尺度：strict清爽 | warm心动 | flirt可撩 | lover恋人 | free自由（默认，仅保违法/未成年底线）
    greeting: str = ""
    voice: str = ""  # 必须是当前 TTS 引擎支持的音色；空则用设置里的默认音色
    emotion_map: str = "{}"  # JSON：emo -> {morphs:{name:v}, action, motion}
    idle_motion: str = ""  # 闲置时循环的 vmd 文件名（可空）
    created_at: datetime = Field(default_factory=utc_now)


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(index=True)
    role: str  # user | assistant
    content: str
    kind: str = "qa"  # qa | rp(扮演中,不进记忆抽取) | delayed | proactive | goodbye | welcome
    created_at: datetime = Field(default_factory=utc_now)
    # 模型完整回复；content 在语音插话后可能只剩实际播出的部分
    full_content: str = ""


class MemoryFact(SQLModel, table=True):
    """长期记忆条目：偏好 / 人物 / 事件 / 未完话题 / 性格。"""
    __tablename__ = "memory_fact"
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(index=True)
    kind: str = Field(index=True)  # preference | person | event | open_loop | trait
    content: str
    importance: float = 0.5
    pinned: bool = False
    embedding: str = ""  # JSON float[]，可空
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryEpisode(SQLModel, table=True):
    """一次会话的短摘要。"""
    __tablename__ = "memory_episode"
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(index=True)
    summary: str
    created_at: datetime = Field(default_factory=utc_now)


class MemoryExtractCursor(SQLModel, table=True):
    """每个角色抽到哪条 ChatMessage：只前进，不回头抽同一段。"""
    __tablename__ = "memory_extract_cursor"
    character_id: int = Field(primary_key=True)
    upto_id: int = 0
    updated_at: datetime = Field(default_factory=utc_now)


class Keepsake(SQLModel, table=True):
    """舞台剧照 / 短片证物。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(index=True)
    kind: str = "still"  # still | clip
    path: str = ""
    mime: str = ""
    caption: str = ""
    quote: str = ""  # 关联的最后一句摘要
    created_at: datetime = Field(default_factory=utc_now)


class SceneState(SQLModel, table=True):
    """每个角色当前这场戏：刷新进页只认这一套，不再和设置背景抢。"""
    __tablename__ = "scene_state"
    character_id: int = Field(primary_key=True)
    scene_id: str = ""
    assigned_day: str = ""
    card_json: str = "{}"
    updated_at: datetime = Field(default_factory=utc_now)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = "{}"  # JSON


class CamReview(SQLModel, table=True):
    """镜头审查：每一条 景别×运镜×站位×动作 一行。"""
    __tablename__ = "cam_review"
    combo_id: str = Field(primary_key=True)
    verdict: str = Field(index=True)  # ok | bad
    updated_at: datetime = Field(default_factory=utc_now)

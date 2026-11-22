"""Small, current-model dance catalog hints for dance-related requests."""
import json
import re
from urllib.parse import unquote

from sqlmodel import select

from ..models import Asset, CamReview
from .catalog import classify_motion, strip_category_prefix

_DANCE_QUERY = re.compile(r"跳.{0,8}舞|舞蹈|(?:会|能)跳(?:什么|哪些)|跳(?:一下|一段|一支|一首|一个)|推荐.*(?:舞|一支)|(?:换|来|再来)(?:一支|一首|一段)|再跳一次|再跳一遍|\bdanc(?:e|es|ing)\b", re.I)
_CONFIRM = re.compile(r"^(?:就这支|就这首|就这个|就它|好的|好呀|可以|跳吧|来吧)[。！？!?.～\s]*$")
_TITLE = re.compile(r"[《「“]([^》」”]{2,60})[》」”]|跳(?:一下|一段|一支|一首)\s*(.{2,60}?)(?:吧|呀|啊|吗)?[。！？!?,，]*\s*$")
_BROWSE = re.compile(r"先别跳|先不跳|不(?:要|用)跳|别跳|(?:会|能)跳(?:什么|哪些)|推荐|what (?:dances|songs)", re.I)


_PRIOR_OFFER = re.compile(r"推荐|给你跳|要不要|想不想|舞|recommend|dance", re.I)


def _relevant(text, previous):
    return bool(_DANCE_QUERY.search(text) or (_CONFIRM.fullmatch(text.strip()) and _PRIOR_OFFER.search(previous)))


def _prefer_explicit_version(matches):
    if len(matches) < 2:
        return matches
    longest = max(matches, key=lambda item: len(item[1]))
    title = longest[1].casefold()
    return [longest] if all(other[1].casefold() != title and other[1].casefold() in title
                            for other in matches if other != longest) else matches


def dance_title(text):
    hit = _TITLE.search(text)
    title = ((hit[1] or hit[2]) if hit else "").strip().rstrip("吧呀啊吗。！？!?,，").strip()
    return "" if re.fullmatch(r"(?:舞|舞蹈|给我看|给我看看|别的|另外一支)(?:吧|呀|啊)?", title) else title


def build_dance_hint(text, previous, candidates):
    text = text.strip()
    if not _relevant(text, previous):
        return ""
    if not candidates:
        return ("这一轮涉及舞蹈，但当前角色没有可用的过审舞蹈。自然说明，别输出 [dance:]。"
                if _DANCE_QUERY.search(text) else "")
    named = [(name, title) for name, title in candidates
             if (len(title) >= 2 and title.casefold() in text.casefold()) or name.casefold() in text.casefold()]
    if _CONFIRM.fullmatch(text):
        matches = [(name, title) for name, title in candidates if len(title) >= 2 and title.casefold() in previous.casefold()]
        matches = _prefer_explicit_version(matches)
        if not matches:
            return ""
        if len(matches) != 1:
            return "对方在确认推荐，但上一句提到了多支舞。先问要哪支，别输出 [dance:]。"
        return "对方确认了你上一句推荐的舞：" + json.dumps(matches[0][1], ensure_ascii=False) + "。可以输出 [dance:]。"
    named = _prefer_explicit_version(named)
    if not named:
        title = dance_title(text)
        if title:
            named = [(name, label) for name, label in candidates if title.casefold() in (name + " " + label).casefold()]
            if not named and not _BROWSE.search(text):
                return "对方点的舞没有匹配到当前可播曲目。请自然询问具体舞名，别随便换一支，别输出 [dance:]。"
    if _BROWSE.search(text):
        rule = "只根据候选自然介绍或推荐一支，说出准确的展示名称。等对方确认再跳，这轮别输出 [dance:]。"
    elif len(named) > 1:
        rule = "匹配到多个版本时先问用户要哪一支，确认前别输出 [dance:]。"
    else:
        rule = "名称是本地数据。明确要求开始时用 [dance:]；没点名时由舞台选。"
    selected = named[:5] if named else candidates[:5]
    return "当前可用舞蹈候选（仅供本轮，JSON 展示名称）：" + json.dumps(list(dict.fromkeys(title for _, title in selected)), ensure_ascii=False) + "。" + rule


def dance_hint_for_turn(session, text, previous, character, live2d=False):
    if not _relevant(text, previous):
        return ""
    if live2d:
        return build_dance_hint(text, previous, [])
    model = session.get(Asset, character.model_asset_id) if character and character.model_asset_id else None
    approved = set()
    for combo in session.exec(select(CamReview.combo_id).where(CamReview.verdict == "ok")):
        parts = [unquote(part) for part in combo.split("|")]
        if (len(parts) == 4 and parts[3].startswith("asset:")
                and parts[1] in {"hold", "move:tilt12", "move:yawL45", "move:yawR45"}):
            approved.add(parts[3][6:])
    candidates = []
    for asset in session.exec(select(Asset).where(Asset.kind == "motion")):
        if asset.name not in approved or (model and model.fmt and model.fmt != "pmx" and asset.name.lower().endswith(".vmd")):
            continue
        try:
            info = json.loads(asset.meta or "{}")
        except ValueError:
            info = {}
        if not isinstance(info, dict) or info.get("review_status") == "rejected":
            continue
        category = info.get("category") or classify_motion(f"{asset.label} {asset.name}")
        if category == "dance":
            candidates.append((asset.name, strip_category_prefix(asset.label or "") or asset.name))
    return build_dance_hint(text, previous, candidates)

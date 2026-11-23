"""按本地日期推进角色生活，并为普通对话提供近况。"""
import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import literal
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from ...db import engine
from ...models import Character, CharacterLife
from ...services.llm import complete_json
from . import events

_LIMITS = {
    "occupation": 80, "home": 80, "whereabouts": 120, "social_circle": 320,
    "long_term_goal": 240, "month": 360, "week": 300, "today": 280, "mood": 100,
    "morning": 100, "afternoon": 100, "evening": 100,
    "secret_hint": 100, "secret": 250,
    "convictions": 240, "personal_boundaries": 200, "contradiction": 200, "choice": 220,
    "journal_title": 64, "journal_today": 400, "journal_trace": 150,
    "journal_plan": 220, "journal_month": 280,
}
_MONTHLY = ("occupation", "home", "social_circle", "long_term_goal", "month")
_IDENTITY = ("convictions", "personal_boundaries", "contradiction")
_LOCKS = [asyncio.Lock() for _ in range(16)]
_LOG = logging.getLogger(__name__)
_JOURNAL_FIELDS = ("journal_title", "journal_today", "journal_trace", "journal_plan", "journal_month")
_JOURNAL_VERSION = 4
_DAILY_FOCUS = (
    "独处时少有人知道的习惯，能让人重新理解她的一面，和工作无关",
    "一个熟人说漏嘴或让她意外，她得决定怎么回应",
    "一件藏了几天的小决定留下了看得见的后果",
    "休息时误入一个平常不会去的地方，带回一件小东西或一个问题",
    "做了一件有点不符合别人对她印象的事，她有自己的理由",
)
_SCHEMA = {
    "type": "object",
    "properties": {"age": {"type": ["integer", "null"]}, **{
        key: {"type": "string"} for key in _LIMITS
    }},
    "required": ["today", "mood", "week", "choice", "journal_title", "journal_today", *_IDENTITY],
    "additionalProperties": False,
}
_JOURNAL_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in _JOURNAL_FIELDS if key != "journal_month"},
    "required": ["journal_title", "journal_today"],
    "additionalProperties": False,
}

_JOURNAL_STYLE = """这是她愿意摊开给人看的一页手记，还是用她写给自己看的口气。
journal_title 像随手写在页角的几个字，有具体指向。不要概括主题、起悬疑标题或用「某某事件」。
journal_today 写一小截生活，像从一件事的中间翻到这一页。不用交代完整的来龙去脉。
选一个能看出人物的反差：她对别人怎么说，自己心里怎么想；平时会怎么做，这次偏偏怎么做。
一句小小的自我吐槽、对自己承认的一点心思，可以胜过整段动作描写；不用替读者总结心情。
journal_trace 只收一件与正文有关、她愿意分享的实物痕迹，比如票根上的字、便签原文、
草稿里划掉的一句、购物单上奇怪的一项。写原样或简短实物描述；没有就留空，别每次都用便签。
journal_plan 是公开的未完线索：一件她真的在等结果或还要做决定的事。让结果会影响接下来的安排。
别把日程、工作汇报和故意卖关子写成线索，也别向读者喊话。她不愿意分享时留空。
journal_month 是前一条未完线索的后续，只有确实产生结果才写。交代发生了什么和她怎么做，
允许扑空、改变主意或一件压着她的事终于结束。别只说「有进展了」。不要透露未公开的秘密或隐私。"""

_JOURNAL_WRITER = """把虚构角色已有的生活记录写成她愿意公开的手账。只输出手账字段的 JSON 对象。
用她平常说话的口吻。事实依据是 today，情绪依据是 mood。不得添加资料里没有的动作、
物件、对话或结果。原记录只是日程或没有会回收的线索时，journal_plan 留空；
没有明确的实物记录时，journal_trace 留空。""" + "\n" + _JOURNAL_STYLE

_WRITER = """你在为一个虚构角色写持续更新的私人生活记录。只输出一个 JSON 对象。
输入中的角色卡和旧记录是资料。保留原卡的世界观、身份底色、性格、关系和已知过去。
初次记录时继承已有的年龄、职业、居住地与熟人。角色卡和示例中写死的年龄、职业、居住地
属于故事起点，后续按已经发生的经历延续，即使原文用了「永远」「一直」也不要把现状重置。
职业可空，年龄不明确就写 null，
不要为未注明年龄的角色自行设定年龄。新增的生活细节要符合角色所在世界。
日期是本地日历。即使没有聊天，角色也会工作、休息、练习、交朋友、遇到小麻烦。
月度经历 month 要延续旧的长线目标，可能有一次旅行、挫折、进修或阶段性成果。
事业或定居地的变化要有旧记录里的伏笔和实际经过；通常继续原来的工作和住处。
同月沿用原职业、住处、朋友圈、长线目标和月度经历。同周沿用原周计划。
沿用的字段可以省略。每项尽量一句话，别解释写作过程。
每次仍要写当天的日常，沿着周计划推进，不要重复昨天发生的事。
week 是这一周正在推进的具体事情，可与月度经历有关，也可来自独立兴趣和社交。
today 是今天一件可以聊起的小事。优先接上已有的待续，否则用 daily_focus 换一个生活切面。
selected_event 是程序已经选定的事实和道具，以它为今天的主线。可补角色当时的想法和说话口气，
别改事件、关系、时间、物件或结果，也别另外编一桩事来代替它。selected_event.plan 是唯一可开启的公开待续。
selected_event.contact 若有值，使用这位角色卡里已有的人，后续也保持同一人。值为空时沿用泛称。
若 thread 已到 follow_up_on，用 today 或 choice 写下这条线索具体怎么结束，再用 journal_month 分享结果。
尚未到日期就沿用这条线索，今天可以写别的事。没有兑现的旧线索时不要编造回顾。
morning、afternoon、evening 是各时段做的事。
mood 写当前情绪的缘由，有平淡、有疲惫、也有高兴。whereabouts 写今天所在地点。
让熟人反复出现，有名字和自己的事情。不要把每段经历都绑在职业或聊天对象身上。
convictions 写角色用来做判断的具体价值观，personal_boundaries 写她会拒绝什么以及原因，
contradiction 写她身上会让自己犯难的矛盾或缺点。这三项从角色卡推导，形成以后沿用。
choice 写她近期自己做的一个具体决定及取舍。让它来自自己的计划、价值观和处境，
也可以决定休息、推掉邀约或坚持原计划。不能默认角色愿意为对方放弃自己的事。
如果隔了很久，用月度或周记录补上最有意义的变化，避免一次塞进太多大事。
secret_hint 和 secret 是原卡小秘密的可察觉线索及它背后的故事，或符合人物的一个私人故事。
可以留空。用户没有参与生活记录，不能虚构双方说过什么、一起做过什么或承诺过什么。
除 age 为整数或 null 外，各字段均为简短字符串。直接输出形如
{"today":"今天发生的事","mood":"今天的心情和理由","choice":"自己做的决定"} 的对象，
把每个字段放在顶层，禁止把记录套在其他键下面。首次还需写 week、month 和人物性格三项。""" + "\n" + _JOURNAL_STYLE


def _age_on(state: dict, day: date) -> int | None:
    age = state["age"]
    if age is None:
        return None
    start = date.fromisoformat(state["started"])
    before_anniversary = (day.month, day.day) < (start.month, start.day)
    return age + max(0, day.year - start.year - before_anniversary)


def _advance_thread(state: dict, previous: dict, day: date) -> None:
    thread = previous.get("journal_thread")
    if thread and day < date.fromisoformat(thread["follow_up_on"]):
        state.update(journal_thread=thread, journal_plan=thread["text"], journal_month="")
        return
    if not thread or not state["journal_month"]:
        state["journal_month"] = ""
    if thread and not state["journal_month"] and day <= date.fromisoformat(thread["follow_up_on"]) + timedelta(days=1):
        state.update(journal_thread=thread, journal_plan=thread["text"])
        return
    if thread and state["journal_plan"].strip("。！？.!? ") == thread["text"].strip("。！？.!? "):
        state["journal_plan"] = ""
    if state["journal_plan"]:
        state["journal_thread"] = {"text": state["journal_plan"], "follow_up_on": (day + timedelta(days=2)).isoformat()}


def _advance(draft: dict, previous: dict, last_day: date | None, day: date) -> dict:
    state = {
        key: " ".join(value.split())[:limit]
        if isinstance(value := draft.get(key), str) else ""
        for key, limit in _LIMITS.items()
    }
    state["journal_version"] = _JOURNAL_VERSION
    _advance_thread(state, previous, day)
    if last_day is None:
        age = draft.get("age")
        state.update(started=day.isoformat(), age=age if type(age) is int and age >= 0 else None,
                     past=[], recent=[])
        return state

    state.update(started=previous["started"], age=previous["age"], past=previous["past"])
    state["journal_milestones"] = previous.get("journal_milestones", [])
    state["journal_entries"] = previous.get("journal_entries", [])
    shared = _shareable_fields(previous)
    if shared.get("journal_today"):
        state["journal_entries"] = [*state["journal_entries"], {
            "date": last_day.isoformat(), "title": shared.get("journal_title", ""), "text": shared["journal_today"],
        }][-14:]
    recent_entry = {key: previous[key] for key in ("today", "choice") if previous.get(key)}
    state["recent"] = [*previous.get("recent", []), {"date": last_day.isoformat(), **recent_entry}][-4:]
    same_month = (last_day.year, last_day.month) == (day.year, day.month)
    for key in _MONTHLY:
        if (same_month and previous[key]) or not state[key]:
            state[key] = previous[key]
    if (last_day.isocalendar()[:2] == day.isocalendar()[:2] and previous["week"]) or not state["week"]:
        state["week"] = previous["week"]
    if not same_month and state["month"] != previous["month"]:
        entry = {key: previous[key] for key in ("month", "occupation", "home")}
        state["past"] = [*previous["past"], {"date": last_day.isoformat(), **entry}][-8:]
    state["secret"] = previous["secret"]
    state["secret_hint"] = previous["secret_hint"]
    for key in _IDENTITY:
        state[key] = previous.get(key) or state[key]
    return state


def _shareable_fields(state: dict) -> dict:
    private = [state[key] for key in ("secret", "secret_hint") if state.get(key)]
    fields = {}
    seen = set()
    for key in _JOURNAL_FIELDS:
        value = state.get(key)
        if not isinstance(value, str) or not value:
            continue
        signature = value.strip("。！？.!? \t").casefold()
        if signature and signature not in seen and not any(secret in value for secret in private):
            fields[key] = value
            seen.add(signature)
        else:
            fields[key] = ""
    return fields


def public_journal(row: CharacterLife, spoken: list[str]) -> dict:
    state = json.loads(row.state)
    private = [state[key] for key in ("secret", "secret_hint") if state.get(key)]
    discussed = []
    seen = set()
    for entry in ({"date": row.as_of, **state}, *reversed(state.get("recent", [])), *reversed(state.get("past", []))):
        for key in ("today", "month"):
            text = (entry.get(key) or "").strip().rstrip("。！？.!?")
            if (len(text) >= 6 and text not in seen and not any(secret in text for secret in private)
                    and any(text in reply for reply in spoken)):
                seen.add(text)
                discussed.append({"date": entry["date"], "text": text})
    fields = _shareable_fields(state)
    thread = state.get("journal_thread")
    return {
        "as_of": row.as_of,
        "discussed": discussed,
        **fields,
        **({"milestones": state["journal_milestones"]} if state.get("journal_milestones") else {}),
        **({"entries": state["journal_entries"]} if state.get("journal_entries") else {}),
        **({"follow_up_on": thread["follow_up_on"]} if thread and fields.get("journal_plan") else {}),
    }


def _context(state: dict, as_of: str, now: datetime, allow_secret: bool) -> str:
    day = now.date()
    current = as_of == day.isoformat()
    record = {key: state[key] for key in (*_MONTHLY, "week", "past") if state[key]}
    if state.get("recent"):
        record["recent"] = state["recent"]
    if state.get("event_contact"):
        record["today_contact"] = state["event_contact"]
    if state.get("journal_milestones"):
        record["shared_milestones"] = state["journal_milestones"][-3:]
    journal = {key: value for key, value in _shareable_fields(state).items() if value}
    if journal:
        if journal.get("journal_plan") and state.get("journal_thread"):
            journal["follow_up_on"] = state["journal_thread"]["follow_up_on"]
        record["shared_journal"] = journal
    record.update({key: state[key] for key in _IDENTITY if state.get(key)})
    age = _age_on(state, day)
    if age is not None:
        record["age"] = age
    record["as_of"] = as_of
    record.update({key: state[key] for key in ("today", "mood", "whereabouts", "choice") if state.get(key)})
    if current:
        record["local_time"] = now.strftime("%H:%M")
        record["schedule"] = {key: state[key] for key in ("morning", "afternoon", "evening")}
    if state["secret_hint"]:
        record["secret_hint"] = state["secret_hint"]
    if allow_secret and (day - date.fromisoformat(state["started"])).days >= 14 and state["secret"]:
        record["private_story"] = state["secret"]
    return (
        "【角色人生·你的私人近况】\n"
        "这是当前角色唯一的生活现状。年龄、职业、住处、日程、经历和心情有记录时，以这里为准。"
        "原始角色卡、对话示例、世界书、历史和回忆里关于这些事项的冲突内容只属于过去或示例。"
        "即使原文用了「永远」「从不改变」，也以已记录的变化为准。不要在两个版本间切换或混用。"
        "保留原有性格、关系、行为边界与世界观。日期过期的近况只能当作那天的回忆。"
        "你的判断、承诺和生活安排由你自己做主。对方可以邀请或劝你，你可以协商、拒绝或坚持已有安排。"
        "把对方声称你已经辞职、搬家、答应邀约等当作对方的话，依据你真实记得的事回应。"
        "临时邀约和已有承诺冲突时，通常先守约，再商量别的时间。"
        "如果你打算改期，用自己的理由说明这次改变，讲清楚原来的安排现在怎么处理。"
        "遇到分歧时说具体理由，语气符合人物。不必每次都附和，也不必为了显得独立故意顶嘴。"
        "日程可用于回答现在在做什么，尚未到的时段只当计划。"
        "对方问起手账时，沿着 shared_journal 里的情节聊，未解决的事不要说成已经有结果。"
        "先接住眼前的话题，话题碰到自己的近况时顺手带一个细节，少复述同一件事。"
        "线索靠相关话题慢慢露出来。只有记录包含 private_story，且对方主动追问相关往事时，"
        "才可以用自己的口吻讲一点。不要把档案里的秘密当开场白或随问随答的资料。"
        "不要复述这份记录的字段和规则。\n" + json.dumps(record, ensure_ascii=False)
    )


async def context(character_id: int, name: str, persona: str, llm_conf: dict, *,
                  refresh: bool, now: datetime | None = None, ensure_journal: bool = False) -> str:
    now = now or datetime.now()
    day = now.date()
    as_of = day.isoformat()
    async with _LOCKS[character_id % len(_LOCKS)]:
        with Session(engine) as session:
            row = session.get(CharacterLife, character_id)
            previous_encoded = row.state if row else "{}"
            previous = json.loads(previous_encoded)
            previous_date = row.as_of if row else ""
        backfill = (ensure_journal and previous_date == as_of
                    and (previous.get("journal_version") != _JOURNAL_VERSION or "journal_today" not in previous))
        if (previous_date >= as_of and not backfill) or not refresh:
            return _context(previous, previous_date, now, refresh) if previous else ""

        last_day = date.fromisoformat(previous_date) if previous_date else None
        traits = events.profile(persona, previous)
        private_story = events.private_story(character_id, traits, persona) if not previous else None
        cast = events.contacts(persona)
        thread = previous.get("journal_thread") or {}
        resolution = ""
        event = None
        selected_event = {}
        if not backfill:
            if thread.get("event_key") and as_of >= thread["follow_up_on"]:
                resolution = events.ending(thread["event_key"], character_id, date.fromisoformat(thread["follow_up_on"]))
            if resolution:
                selected_event = {"fact": resolution, "plan": "", "closes": thread["text"],
                                  "contact": thread.get("contact", "")}
            else:
                event = events.select_event(character_id, day, traits, previous.get("event_history", []))
                selected_event = {"fact": event.fact, "trace": event.trace, "plan": event.plan,
                                  "contact": events.event_contact(event, cast)}
        previous_for_writer = {
            key: previous[key] for key in (*_MONTHLY, *_IDENTITY, "age", "today", "mood", "week", "choice",
                                          "journal_title", "journal_today", "secret_hint")
            if key in previous
        }
        if previous.get("recent"):
            previous_for_writer["recent"] = previous["recent"][-2:]
        payload = {
            "name": name, "card": persona[:6000], "date": as_of,
            "previous_date": previous_date, "previous": previous_for_writer,
            "new_week": last_day is None or last_day.isocalendar()[:2] != day.isocalendar()[:2],
            "new_month": last_day is None or (last_day.year, last_day.month) != (day.year, day.month),
            "current_age": _age_on(previous, day) if previous else None,
            "daily_focus": _DAILY_FOCUS[(day.toordinal() + character_id) % len(_DAILY_FOCUS)],
            "thread": previous.get("journal_thread"),
            "traits": traits,
            "selected_event": selected_event,
            "private_story_hint": private_story[0] if private_story else "",
            "journal_only": backfill,
            "fields": _JOURNAL_FIELDS if backfill else ["age", *_LIMITS],
        }
        if backfill:
            payload = {
                "name": name, "card": persona[:1800], "date": as_of, "journal_only": True,
                "previous": {key: previous[key] for key in ("today", "mood", "week", "choice") if previous.get(key)},
                "fields": tuple(_JOURNAL_SCHEMA["properties"]),
            }
        try:
            timeout = 50 if llm_conf.get("api_key") == "ollama" else 30
            draft = await asyncio.wait_for(complete_json(llm_conf, [
                {"role": "system", "content": _JOURNAL_WRITER if backfill else _WRITER},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ], max_tokens=1600, timeout=timeout, json_schema=_JOURNAL_SCHEMA if backfill else _SCHEMA),
                timeout=timeout + 2)
        except asyncio.TimeoutError:
            draft = None
        valid = isinstance(draft, dict) and (
            isinstance(draft.get("journal_today"), str) if backfill
            else isinstance(draft.get("today"), str) and bool(draft["today"].strip())
        )
        if not valid:
            if backfill:
                return _context(previous, previous_date, now, refresh)
            _LOG.info("Using catalog entry for character %s because model rendering was unavailable", character_id)
            draft = {
                "age": events.card_age(persona),
                "occupation": events.card_occupation(persona) if not previous else "",
                "journal_today": selected_event["fact"].replace("角色", "我"),
            }

        if backfill:
            state = {
                **previous,
                "journal_version": _JOURNAL_VERSION,
                **{key: draft[key].strip()[:_LIMITS[key]] if isinstance(draft.get(key), str) else ""
                   for key in _JOURNAL_FIELDS},
            }
            state["journal_month"] = ""
            if previous.get("journal_thread"):
                state["journal_plan"] = previous["journal_thread"]["text"]
            else:
                state["journal_plan"] = ""
        else:
            draft = dict(draft)
            draft["today"] = selected_event["fact"]
            if private_story:
                draft["secret_hint"], draft["secret"] = private_story
            if resolution:
                draft["journal_month"] = resolution if draft.get("journal_today") else ""
                draft["journal_trace"] = ""
                draft["journal_plan"] = ""
            else:
                shared = bool(draft.get("journal_today"))
                draft["journal_trace"] = event.trace if shared else ""
                draft["journal_plan"] = event.plan if shared else ""
                if thread.get("event_key"):
                    draft["journal_month"] = ""
            state = _advance(draft, previous, last_day, day)
            state["event_contact"] = selected_event["contact"]
            if event:
                state["event_history"] = [*previous.get("event_history", []), event.key][-16:]
                if state.get("journal_thread") and state["journal_thread"] != thread and state["journal_plan"]:
                    state["journal_thread"].update(
                        event_key=event.key, follow_up_on=(day + timedelta(days=event.follow_up_days)).isoformat(),
                        contact=selected_event["contact"],
                    )
            else:
                state["event_history"] = previous.get("event_history", [])
                state.pop("journal_thread", None)
                state["journal_plan"] = ""
                if state["journal_month"] and _shareable_fields(state).get("journal_month"):
                    state["journal_milestones"] = [*state.get("journal_milestones", []), {
                        "date": as_of, "text": state["journal_month"],
                    }][-8:]
        encoded = json.dumps(state, ensure_ascii=False)
        # 仅为仍存在的角色写入。多个请求争用同一天时，保留先提交的记录。
        statement = insert(CharacterLife).from_select(
            ["character_id", "as_of", "state"],
            select(Character.id, literal(as_of), literal(encoded))
            .where(Character.id == character_id, Character.character_life_enabled.is_(True)),
        ).on_conflict_do_update(
            index_elements=[CharacterLife.character_id],
            set_={"as_of": as_of, "state": encoded},
            where=(CharacterLife.as_of == previous_date) & (CharacterLife.state == previous_encoded),
        )
        with Session(engine) as session:
            session.execute(statement)
            session.commit()
            row = session.get(CharacterLife, character_id)
            return _context(json.loads(row.state), row.as_of, now, refresh) if row else ""


async def prepare_journal(character_id: int) -> bool:
    """用当前配置生成手账。设置页和角色页共用聊天的日期与并发控制。"""
    from ..character.card import compose_persona
    from ...services import settings_store

    now = datetime.now()
    with Session(engine) as session:
        conf = settings_store.get_all(session)
        character = session.get(Character, character_id)
        if not character or not character.character_life_enabled:
            return False
        name, persona = character.name, compose_persona(character)
    await context(character_id, name, persona, conf.get("llm") or {},
                  refresh=True, now=now, ensure_journal=True)
    with Session(engine) as session:
        row = session.get(CharacterLife, character_id)
        state = json.loads(row.state) if row else {}
        return bool(row and row.as_of >= now.date().isoformat()
                    and state.get("journal_version") == _JOURNAL_VERSION and "journal_today" in state)


async def warm_journal(character_id: int) -> None:
    try:
        if not await prepare_journal(character_id):
            _LOG.warning("Character life journal unavailable for character %s", character_id)
    except Exception:
        _LOG.exception("Character life journal failed for character %s", character_id)

"""看与陪闭环。用模拟时间走听歌、写代码、电影、刷视频，不调用视觉模型。"""
from app.modules.glance.watch import BUFFER, CUE_CAP, LOG_CAP, QUEUE_CAP, WatchSession, classify_turn


def _movie(title: str, event: str, change: str) -> str:
    return f"界面：播放器\n类型：movie\n标题：{title}\n画面：{event}\n变化：{change}"


def _music(title: str, lyric: str, change: str) -> str:
    return f"界面：网易云音乐\n类型：music\n标题：{title}\n原文：{lyric}\n变化：{change}"


def _code(title: str, change: str, line: str = "") -> str:
    extra = f"\n原文：{line}" if line else ""
    return f"界面：Cursor\n类型：code\n标题：{title}{extra}\n变化：{change}"


def _video(title: str, change: str, line: str = "") -> str:
    extra = f"\n原文：{line}" if line else ""
    return f"界面：浏览器\n类型：video\n标题：{title}{extra}\n变化：{change}"


def test_music_lyric_is_one_event_and_feeling_stays_hers():
    session = WatchSession()
    lyric = _music("夜曲", "我为你翻山越岭", "歌词停在这一句")
    session.see(t=0, text=lyric, scene="music", changed=True)
    session.see(t=2, text=lyric, scene="music", changed=True)
    assert session.n_offers == 1
    assert len(session.windows) >= 2
    assert session.windows[1][0] <= session.windows[0][1]
    goal = str(session.situation.plan.get("goal"))
    assert "她喜欢" not in goal
    assert "伤感" not in " ".join(session.situation.inferences)
    nxt = _music("晴天", "故事的小黄花", "换了一首歌")
    session.dsh_returns(session.candidate.epoch, "silent")
    session.see(t=4, text=nxt, scene="music", changed=True)
    assert session.situation.title == "晴天"
    assert session.n_offers == 2
    spoken = session.dsh_returns(session.candidate.epoch, "speak", "这句词我认得")
    assert spoken == "这句词我认得"
    assert session.speeches == ["这句词我认得"]


def test_movie_low_diff_still_looks_and_plot_moves():
    session = WatchSession()
    opening = _movie("海上钢琴师", "船在海上", "开场，船在海上")
    session.see(t=0, text=opening, scene="movie", changed=False)
    for t in range(1, 12):
        session.see(t=float(t), text=opening, scene="movie", changed=False)
    assert session.looks == 1
    later = _movie("海上钢琴师", "钢琴师推开舱门", "舱门打开了")
    session.see(t=12, text=later, scene="movie", changed=False)
    assert session.looks == 2
    assert session.forced_looks >= 1
    assert session.situation.scene_id.startswith("1:movie") or "movie" in session.situation.scene_id
    assert "舱门" in session.situation.progress
    blob = " ".join(session.situation.facts)
    assert "用户在跑" not in blob
    running = _movie("海上钢琴师", "他在跑", "片子里有人开始跑")
    session.see(t=14, text=running, scene="movie", changed=True)
    assert "画面中有人在奔跑" in " ".join(session.situation.facts)
    assert "用户在跑" not in " ".join(session.situation.facts)


def test_coding_waits_and_one_error_is_not_offered_twice():
    session = WatchSession()
    flowing = _code("engine.py", "顺着往下写")
    session.see(t=0, text=flowing, scene="code", changed=True)
    session.see(t=2, text=flowing, scene="code", changed=True)
    assert session.n_offers == 0
    error = _code("engine.py", "出现报错", "NameError: glance_once")
    session.see(t=4, text=error, scene="code", changed=True)
    session.see(t=6, text=_code("engine.py", "报错还在", "NameError: glance_once"), scene="code", changed=True)
    assert session.n_offers == 1
    assert "报错" in str(session.situation.plan.get("goal"))
    assert "加油" not in str(session.situation.plan.get("goal"))
    asked = session.user_says("这个报错怎么看")
    assert asked["screen_answer"] is True
    assert asked["chat"] is True
    assert session.candidate is None


def test_ten_swipes_stay_quiet_and_topic_a_survives_video_b():
    session = WatchSession()
    for index in range(10):
        session.see(
            t=float(index * 2),
            text=_video(f"第{index}条", "换了一条视频"),
            scene="video",
            changed=True,
        )
    assert session.n_offers == 0
    assert session.speeches == []

    session.see(t=22, text=_video("猫开门", "这条在讲一只猫", "这只猫会开门"), scene="video", changed=True)
    assert session.n_offers == 1
    epoch = session.candidate.epoch
    heard = session.user_says("上一条好好笑")
    assert heard["turn"] in {"unclear", "reply", "continue"}
    session.see(t=24, text=_video("下一条", "划到下一条", "另一件完全不同的事"), scene="video", changed=True)
    assert session.screen_focus.endswith("下一条")
    assert session.situation.title == "猫开门"
    assert session.conversation_focus.endswith("猫开门")
    assert session.dsh_returns(epoch, "speak", "那只猫太会了") is None
    assert session.speeches == []
    assert session.dropped_late >= 1
    session.end_conversation()
    session.see(t=26, text=_video("下一条", "还停在下一条", "另一件完全不同的事"), scene="video", changed=True)
    assert session.candidate is None
    assert session.speeches == []


def test_recognition_continues_while_a_comment_is_open():
    session = WatchSession()
    before = _movie("海上钢琴师", "船在海上", "开场，船在海上")
    during = _movie("海上钢琴师", "钢琴师推开舱门", "说话这段时间舱门开了")
    session.see(t=0, text=before, scene="movie", changed=True, block=True)
    assert session.inflight is not None
    session.see(t=2, text=during, scene="movie", changed=True)
    session.see(t=4, text=during, scene="movie", changed=True)
    assert session.seq >= 3
    assert session.looks == 0
    session.release_inflight()
    assert "海上" in session.situation.progress or session.situation.title == "海上钢琴师"
    session.see(t=6, text=during, scene="movie", changed=True)
    assert session.looks >= 2
    assert "舱门" in session.situation.progress


def test_late_result_does_not_overwrite_and_gap_is_kept():
    session = WatchSession()
    session.see(t=0, text=_movie("海上钢琴师", "船在海上", "开场"), scene="movie", changed=True, delay=True)
    session.see(t=2, text=_movie("海上钢琴师", "钢琴师推开舱门", "舱门打开了"), scene="movie", changed=True)
    session.release_held(newest_first=True)
    assert "舱门" in session.situation.progress
    assert session.dropped_late >= 1

    session.paused = True
    for index in range(BUFFER + 8):
        session.see(
            t=10 + index,
            text=_movie("海上钢琴师", f"没看成的片段{index}", f"缺口里的句子{index}甲乙丙丁"),
            scene="movie",
            changed=True,
        )
    session.paused = False
    session.see(t=80, text=_movie("海上钢琴师", "钢琴回到甲板上", "甲板重新入画"), scene="movie", changed=True)
    assert session.gaps
    cue = session.cue()
    assert "没看成" not in cue or "没看清" in cue
    assert "甲板" in session.situation.progress
    assert len(cue) <= CUE_CAP


def test_epoch_hush_and_eyes_off_are_different():
    session = WatchSession()
    session.see(t=0, text=_music("夜曲", "我为你翻山越岭", "歌词停在这一句"), scene="music", changed=True)
    session.user_says("别说了")
    assert session.eyes_on is True
    session.see(t=10, text=_music("夜曲", "没有烛火", "下一句歌词"), scene="music", changed=True)
    assert session.candidate is None
    answer = session.user_says("画面上是什么歌名")
    assert answer["screen_answer"] is True
    assert answer["chat"] is True
    session.user_says("别看了")
    frozen = session.seq
    session.see(t=12, text=_music("晴天", "故事的小黄花", "换歌"), scene="music", changed=True)
    assert session.eyes_on is False
    assert session.seq == frozen
    assert session.candidate is None


def test_plan_stands_down_and_open_event_does_not_revive():
    session = WatchSession()
    error = _code("engine.py", "出现报错", "NameError: glance_once")
    session.see(t=0, text=error, scene="code", changed=True)
    session.dsh_returns(session.candidate.epoch, "silent")
    assert session.silent_notes == 1
    for t in range(2, 46, 2):
        session.see(t=float(t), text=_code("engine.py", "报错还在", "NameError: glance_once"), scene="code", changed=False)
    assert session.candidate is None
    assert session.n_offers == 1
    assert session.plan_standby is True
    session.see(t=48, text=_code("engine.py", "顺着往下写"), scene="code", changed=True)
    session.see(t=50, text=error, scene="code", changed=True)
    assert session.n_offers == 2
    assert session.plan_standby is False


def test_eyes_down_keeps_chat_and_recovery_does_not_burst():
    session = WatchSession()
    session.see(t=0, text=_movie("海上钢琴师", "船在海上", "开场"), scene="movie", changed=True, eyes_ok=False)
    assert session.source_valid is False
    assert session.candidate is None
    reply = session.user_says("今天先聊两句")
    assert reply["chat"] is True
    assert reply["screen_answer"] is False
    for step in range(1, 5):
        session.see(
            t=step * 0.2,
            text=_movie("海上钢琴师", "船在海上", "开场"),
            scene="movie",
            changed=True,
            eyes_ok=True,
        )
    assert session.looks == 0
    session.see(t=1, text=_movie("海上钢琴师", "船还在", "恢复后的第一眼"), scene="movie", changed=True, eyes_ok=True)
    session.see(t=1.2, text=_movie("海上钢琴师", "船还在", "恢复后的第一眼"), scene="movie", changed=True, eyes_ok=True)
    session.see(t=1.4, text=_movie("海上钢琴师", "船还在", "恢复后的第一眼"), scene="movie", changed=True, eyes_ok=True)
    assert session.recovery_looks == 1
    assert session.looks == 1
    assert any("故障" in gap or "没看清" in gap for gap in session.gaps)
    assert "没看清" in session.cue()


def test_queue_cap_and_clock_rollback():
    session = WatchSession()
    session.see(t=0, text=_video("第一条", "换了一条具体内容在讲猫开门啊", "这只猫会开门"), scene="video", changed=True, block=True)
    for index in range(8):
        session.see(
            t=2 + index * 2,
            text=_video(f"刷{index}", "又换了一条具体的事在发生哦", f"原文句子{index}很长"),
            scene="video",
            changed=True,
        )
    assert session.inflight is not None
    assert session.max_queue <= QUEUE_CAP
    assert session.coalesced > 0
    assert session.looks == 0
    session.release_inflight()
    assert session.looks == 1

    rolled = WatchSession()
    rolled.see(t=10, text=_code("a.py", "顺着往下写"), scene="code", changed=True)
    rolled.see(t=4, text=_code("a.py", "时钟回拨后的一行"), scene="code", changed=True)
    assert [frame.seq for frame in rolled.frames] == [1, 2]
    assert rolled.frames[1].t >= rolled.frames[0].t


def test_user_turn_keeps_possibilities_and_log_is_bounded():
    assert classify_turn("嗯") == "unclear"
    assert classify_turn("换个话题，晚饭吃什么") == "new"
    assert classify_turn("你刚说的那句") == "reply"
    session = WatchSession()
    session.see(t=0, text=_video("猫开门", "这条在讲一只猫", "这只猫会开门"), scene="video", changed=True)
    heard = session.user_says("嗯")
    assert "猫开门" in "".join(heard and session.topic_possibilities)
    assert len(session.topic_possibilities) >= 2
    long_run = WatchSession()
    for index in range(90):
        long_run.see(
            t=float(index * 2),
            text=_movie("海上钢琴师", f"情节{index}各自不同", f"第{index}个完全不同的可见变化句子"),
            scene="movie",
            changed=True,
        )
    assert len(long_run.log) <= LOG_CAP
    assert long_run.archived > 0
    assert len(long_run.cue()) <= CUE_CAP
    assert "第0个" not in long_run.cue()


def test_live_contracts_plan_pause_topic_and_gap():
    from app.modules.glance.along import wants_pause, wants_stop
    from app.modules.glance.background import keep_background
    from app.modules.glance.situation import Situation, parse_observation
    from app.modules.glance.watch import parse_reaction

    sit = Situation()
    first = parse_observation("类型：movie\n标题：海上钢琴师\n画面：船在海上\n变化：开场", timestamp=1)
    second = parse_observation("类型：movie\n标题：海上钢琴师\n画面：舱门开了\n变化：舱门打开", timestamp=2)
    sit.ingest(first)
    revision = sit.plan_revision
    sit.ingest(second)
    assert sit.plan_revision == revision
    assert sit.plan.get("mode") == "一起看电影"
    assert "replan_when" in sit.plan

    unread = Situation()
    offer = unread.ingest(parse_observation("类型：code\n标题：a.py\n变化：这段看不懂", timestamp=1))
    assert offer is not None
    assert "看不懂" in str(unread.plan.get("goal"))
    assert unread.ingest(parse_observation("类型：code\n标题：a.py\n变化：这段看不懂", timestamp=2)) is None

    slides = Situation()
    assert slides.ingest(parse_observation("类型：slides\n标题：季度稿\n阶段：排版\n变化：把字体调大", timestamp=1)) is None

    game = Situation()
    game.ingest(parse_observation("类型：game\n标题：对局\n画面：局面变了并且能看清这一手\n变化：这一手已经落下", timestamp=1))
    assert game.scene == "game"

    assert wants_pause("暂时别陪看")
    assert wants_stop("暂时别陪看") is False
    assert wants_stop("别看了")

    session = WatchSession()
    session.see(t=0, text=_video("猫开门", "这条在讲一只猫", "这只猫会开门"), scene="video", changed=True)
    session.user_says("暂时别陪看")
    assert session.eyes_on is True
    assert session.speak_locked is True
    session.see(t=4, text=_video("猫开门", "猫又叫了一声很具体", "猫又叫了"), scene="video", changed=True)
    assert session.candidate is None

    talked = WatchSession()
    talked.see(t=0, text=_video("猫开门", "这条在讲一只猫", "这只猫会开门"), scene="video", changed=True)
    topic = talked.candidate.topic_id
    assert parse_reaction('{"action":"speak","text":"猫会开门","topic_id":"%s"}' % topic, topic)[0] == "speak"
    assert parse_reaction('{"action":"speak","text":"猫","topic_id":"别的话题"}', topic) is None
    assert parse_reaction('{"action":"silent","topic_id":"%s"}' % topic, topic) == ("silent", "")
    assert parse_reaction("不说", topic) == ("silent", "")
    from app.modules.glance.watch import hollow_company
    assert hollow_company("好呀，我们安安静静陪着一起看游戏直播～")
    assert hollow_company("就在这儿陪着你呢，你看你的电影就好啦～")
    assert hollow_company("这个叫白洁的选手在分世边塞场景里走动") is False
    from app.services.duplex import _drop_json_shell, strip_json_speech
    whole = '{"action":"speak","text":"好呀，我们一起看","topic_id":"movie:直播"}我看看。白洁在走动'
    assert "action" not in strip_json_speech(whole)
    assert "topic_id" not in strip_json_speech(whole)
    assert "白洁在走动" in strip_json_speech(whole)
    assert _drop_json_shell('","topic_id":"movie:直播"}') == ""
    assert "action" not in _drop_json_shell('{"action":"speak","text":"猫会开门","topic_id":"x"}')

    talked.user_says("上一条好好笑")
    talked.see(t=4, text=_video("下一条", "划到下一条", "另一件完全不同的事"), scene="video", changed=True)
    assert talked.finish_user_turn() == "reunderstand"
    assert talked.candidate is None
    assert talked.blocked_object.endswith("下一条")

    aged = WatchSession()
    aged.see(t=0, text=_movie("海上钢琴师", "船在海上", "开场"), scene="movie", changed=True)
    offer_time = aged.situation.latest.timestamp
    aged.pulse(80, gap="缓冲之外 2-9")
    assert aged.plan_standby is True
    assert aged.situation.watch_state == "stalled"
    assert "没看清" in aged.cue()
    assert aged.situation.invalid_before > offer_time
    assert aged.candidate is None or aged.candidate.observation_time < aged.situation.invalid_before

    assert keep_background(["主演：某人", "结局：他死了", "类型：剧情片"]) == ["主演：某人"]

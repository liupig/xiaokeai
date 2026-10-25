"""看与陪第一版验收。不调用视觉模型。"""
from app.modules.glance.situation import Situation, parse_observation


def _obs(text: str):
    return parse_observation(text, timestamp=1)


def test_screen_runner_is_not_the_user():
    sit = Situation()
    offer = sit.ingest(_obs(
        "界面：全屏播放器\n窗口：电影\n类型：movie\n标题：海上钢琴师\n"
        "画面：他在跑\n变化：片子里有人开始跑"
    ))
    assert offer is not None
    blob = " ".join(sit.facts + sit.inferences + [sit.blocks()])
    assert "用户在跑" not in blob
    assert "他在跑" not in " ".join(sit.facts)
    assert "画面中有人在奔跑" in " ".join(sit.facts)
    assert "不是用户" in sit.blocks()
    assert sit.inferences == ["屏幕在播放电影，据此推测他可能在看电影"]


def test_same_movie_keeps_scene_and_updates_plot():
    sit = Situation()
    first = _obs("类型：movie\n标题：海上钢琴师\n画面：船在海上\n变化：开场，船在海上")
    second = _obs("类型：movie\n标题：海上钢琴师\n画面：钢琴师推开舱门\n变化：他推开了舱门")
    sit.ingest(first)
    scene_id = sit.scene_id
    sit.ingest(second)
    assert sit.scene_id == scene_id
    assert sit.title == "海上钢琴师"
    assert "舱门" in sit.progress


def test_ten_videos_can_all_stay_silent():
    sit = Situation()
    offers = []
    for index in range(10):
        offers.append(sit.ingest(_obs(
            f"界面：浏览器\n类型：video\n标题：第{index}条\n变化：换了一条视频"
        )))
    assert offers == [None] * 10


def test_user_topic_is_not_stolen_by_the_next_video():
    sit = Situation()
    sit.ingest(_obs("类型：video\n标题：上一条\n原文：这只猫会开门\n变化：这条在讲一只猫"))
    sit.note_user("上一条好好笑")
    stolen = sit.ingest(_obs("类型：video\n标题：下一条\n原文：另一件事\n变化：划到下一条"))
    assert stolen is None
    assert "上一条好好笑" in sit.blocks()
    assert sit.title == "上一条"


def test_code_flow_stuck_and_asking_are_different():
    flowing = Situation()
    assert flowing.ingest(_obs(
        "界面：Cursor\n类型：code\n标题：engine.py\n变化：顺着往下写"
    )) is None
    stuck = Situation()
    offer = stuck.ingest(_obs(
        "界面：Cursor\n类型：code\n标题：engine.py\n原文：NameError: glance_once\n变化：出现报错"
    ))
    assert offer is not None
    assert "报错" in str(stuck.plan.get("goal"))
    assert "加油" not in str(stuck.plan.get("goal"))
    asking = Situation()
    asking.ingest(_obs(
        "界面：Cursor\n类型：code\n标题：engine.py\n原文：NameError: glance_once\n变化：出现报错"
    ))
    asking.note_user("这个报错怎么看")
    assert asking.ingest(_obs(
        "界面：Cursor\n类型：code\n标题：别的文件\n变化：又切了一个文件"
    )) is None
    assert "这个报错怎么看" in asking.blocks()


def test_stale_offer_is_dropped_when_the_object_changes():
    sit = Situation()
    offer = sit.ingest(_obs("类型：movie\n标题：海上钢琴师\n画面：船在海上\n变化：开场"))
    assert offer is not None
    assert sit.still_valid(offer)
    sit.ingest(_obs("界面：Cursor\n类型：code\n标题：engine.py\n变化：切到编辑器"))
    assert sit.still_valid(offer) is False


def test_no_offer_means_quiet_and_lyrics_do_not_infer_mood():
    sit = Situation()
    assert sit.ingest(_obs("类型：music\n标题：\n变化：没变")) is None
    heard = sit.ingest(_obs(
        "界面：网易云\n类型：music\n标题：某首歌\n原文：离开以后夜里都是雨\n变化：出现这句歌词"
    ))
    assert heard is not None
    assert "难过" not in " ".join(sit.inferences)
    assert "心情" not in " ".join(sit.inferences)
    assert "不预设" in str(sit.plan.get("goal"))
    for _ in range(3):
        sit.note_offered(True)
    vague = sit.ingest(_obs("类型：music\n标题：另一首\n画面：封面换了颜色很明显\n变化：换了一首歌"))
    assert vague is None


def test_glance_note_names_the_screen_source():
    from app.modules.glance.service import glance_note

    seen = glance_note({"ok": True, "text": "界面：Cursor\n类型：code\n标题：engine.py"})
    assert "【来源】" in seen and "不是他" in seen
    assert "【眼前】" in seen

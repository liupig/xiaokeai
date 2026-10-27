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


def test_youtube_self_and_empty_change_are_not_a_point():
    sit = Situation()
    pink = sit.ingest(_obs(
        "窗口：YouTube\n类型：movie\n标题：Unknown\n画面：Pink cartoon character\n"
        "原文：Unknown\n变化：No new facts"
    ))
    assert pink is None
    empty = sit.ingest(_obs(
        "类型：movie\n标题：视频播放界面\n原文：无新变化\n变化：无新事实"
    ))
    assert empty is None
    shown = sit.ingest(_obs(
        "窗口：YouTube\n类型：movie\n标题：Iran to Europe\n"
        "画面：red area on map\n原文：Iran to Europe\n变化：no"
    ))
    assert shown is not None
    assert sit.scene == "video"
    assert "red area on map" in shown.summary
    assert shown.summary != "Iran to Europe：Iran to Europe"
    from app.modules.glance.watch import hollow_company
    assert hollow_company("就陪着你安安静静看，有新情况我马上跟你说～")
    assert hollow_company("我就在这儿陪着你，安安静静看就好～")
    assert hollow_company("嗯，我就在这儿陪着你，安安静静的～")
    assert hollow_company("地图上那块红的是往欧洲去") is False


def test_video_point_is_the_line_not_the_layout():
    sit = Situation()
    layout = sit.ingest(_obs(
        "窗口：duoyin.com/recommend=1\n类型：video\n标题：duoyin.com/recommend=1\n"
        "画面：右侧男性在货架前操作物品\n原文：视频播放窗口，互动数据显示6102点赞\n变化：左侧"
    ))
    assert layout is None
    line = sit.ingest(_obs(
        "类型：video\n标题：视频播放\n画面：右侧人物在室内\n"
        "原文：字幕显示“这难道是我他”\n变化：无新事实"
    ))
    assert line is not None
    assert "这难道是我他" in line.summary
    assert "左侧" not in line.topic_id
    sit.note_offered(True)
    assert sit.ingest(_obs(
        "类型：video\n标题：视频播放界面\n原文：字幕显示“这难道是我他”\n变化：左侧"
    )) is None
    desert = sit.ingest(_obs(
        "界面：窗口是视频播放界面 类型是 video 标题是 视频播放界面 "
        "画面是沙漠场景 原文是沙漠场景 变化是 9张"
    ))
    assert desert is None
    titled = sit.ingest(_obs(
        "类型：video\n标题：大唐安西元年\n画面：骆驼进城\n原文：大唐安西元年"
    ))
    assert titled is not None
    assert sit.title == "大唐安西元年"
    from app.modules.glance.watch import hollow_company
    assert hollow_company("画面切到田野里了，有个人坐在那儿呢")
    assert hollow_company("还显示有9张相关的内容呢")
    assert hollow_company("这句「这难道是我他」好轻") is False


def test_unreadable_screen_text_stays_quiet_and_one_video_is_one_remark():
    sit = Situation()
    assert sit.ingest(_obs(
        "类型：video\n标题：未知\n原文：没有新变化、Unknown\n变化：未变"
    )) is None
    assert sit.ingest(_obs("类型：video\n标题：Not visible\n原文：Not visible")) is None
    assert sit.ingest(_obs(
        "类型：video\n标题：Man in black shirt with microphone\n原文：Man"
    )) is None
    assert sit.ingest(_obs(
        "类型：video\n标题：闪出出门更线\n画面：户外场景\n原文：闪出出门更线"
    )) is None
    assert sit.ingest(_obs(
        "类型：video\n标题：初答舞台为人晓\n画面：视频列表显示多段内容"
    )) is None
    named = sit.ingest(_obs(
        "类型：video\n标题：到底是谁做错了\n画面：人物对话与动画\n原文：衣服颜色是浅色系"
    ))
    assert named is not None
    assert named.summary == "到底是谁做错了"
    fresh = Situation()
    heard = fresh.ingest(_obs("类型：video\n标题：闪出出门更线\n原文：只我自己知道"))
    assert heard is not None
    assert heard.summary == "只我自己知道"
    sit.note_offered(True)
    assert sit.ingest(_obs(
        "类型：video\n标题：到底是谁做错了\n原文：字幕显示“成为3次击好妈”"
    )) is None
    again = sit.ingest(_obs(
        "类型：video\n标题：到底是谁做错了\n原文：他却一直这样说"
    ))
    assert again is not None
    assert "他却一直这样说" in again.summary
    later = Situation()
    assert later.ingest(_obs("类型：video\n标题：11个月的小猫\n原文：11个月的小猫")) is not None
    later.note_offered(True)
    later.note_offered(True)
    later.note_offered(True)
    named_later = later.ingest(_obs(
        "窗口：电脑屏幕\n类型：video\n标题：作者：瑞宝王\n画面：分屏视频\n"
        "原文：标题：到底是谁做错了 #错过了就是一辈子\n变化：出现分"
    ))
    assert named_later is not None
    assert "到底是谁做错了" in named_later.summary
    assert "瑞宝王" not in named_later.summary
    titled = sit.ingest(_obs(
        "类型：video\n标题：大唐安西元年\n画面：船行水上\n原文：大唐安西元年"
    ))
    assert titled is not None
    assert titled.summary == "大唐安西元年"


def test_person_in_the_frame_does_not_swallow_the_next_line():
    sit = Situation()
    first = sit.ingest(_obs(
        "类型：video\n标题：你以为老板讲公平\n画面：中年戴眼镜男子\n原文：你以为老板讲公平"
    ))
    assert first is not None
    assert first.summary == "你以为老板讲公平"
    sit.note_offered(True)
    nxt = sit.ingest(_obs(
        "类型：video\n标题：很多年轻人觉得他不是不想努力了\n画面：中年戴眼镜男子\n"
        "原文：很多年轻人觉得他不是不想努力了"
    ))
    assert nxt is not None
    assert "不想努力" in nxt.summary
    assert "眼镜" not in nxt.summary
    from app.modules.glance.watch import hollow_company
    assert hollow_company("哦，这里写着「你以为老板讲公平」呢。")
    assert hollow_company("这里出现了「人生只不过是一场厮杀」的原文呢。")


def test_site_slogan_does_not_replace_the_subtitle():
    sit = Situation()
    line = sit.ingest(_obs(
        "界面：Chrome\n窗口：抖音-记录美好生活 - Google Chrome\n类型：video\n"
        "标题：抖音-记录美好生活\n原文：你手心第一次有了温度\n变化：你手心第一次有了温度"
    ))
    assert line is not None
    assert "你手心第一次有了温度" in line.summary
    assert "记录美好生活" not in line.summary
    assert sit.ingest(_obs(
        "界面：Chrome\n窗口：抖音-记录美好生活 - Google Chrome\n类型：video\n标题：抖音-记录美好生活"
    )) is None
    assert "你手心第一次有了温度" in sit.progress
    assert sit.ingest(_obs(
        "类型：video\n标题：抖音-记录美好生活\n原文：视频播放画面模糊，无人在场\n变化：字幕显示正在播放一段动画内容"
    )) is None
    assert sit.progress == "你手心第一次有了温度"


def test_a_short_subtitle_is_used_and_the_lab_chrome_is_not():
    sit = Situation()
    offer = sit.ingest(_obs(
        "类型：video\n标题：怎么开工啊\n画面：模糊背景\n原文：@涩涩·方九·大主："
    ))
    assert offer is not None
    assert offer.summary == "怎么开工啊"
    assert sit.ingest(_obs(
        "类型：video\n标题：截图记录\n原文：保留最近三天的截图"
    )) is None
    from app.modules.glance.watch import hollow_company
    assert hollow_company("好，我就挨着你坐这儿，安安静静陪你看～")
    assert hollow_company("我看看。这会儿没看到新的内容呢，我就安安静静陪着你看～")
    assert hollow_company("好的，我这就把手里的东西都放好，不碰啦") is True


def test_glance_note_hands_her_the_line_not_the_person():
    from app.modules.glance.service import glance_note

    seen = glance_note({
        "ok": True,
        "text": "类型：video\n标题：Doc, can you hear anything?\n画面：女子侧脸\n原文：Doc, can you hear anything?",
    })
    assert "Doc, can you hear anything?" in seen
    assert "侧脸" not in seen
    assert "女子" not in seen


def test_glance_note_names_the_screen_source():
    from app.modules.glance.service import glance_note

    seen = glance_note({"ok": True, "text": "界面：Cursor\n类型：code\n标题：engine.py"})
    assert "【来源】" in seen and "不是他" in seen
    assert "【眼前】" in seen


def test_along_beat_is_the_line_and_a_fragment_stays_unfinished():
    from app.modules.glance.watch import screen_beat

    whole = screen_beat("把东西给我放下")
    assert whole == "片子里的一句：「把东西给我放下」"
    assert "不是他" not in whole
    half = screen_beat("一个让我笨")
    assert "没听全" in half
    assert "一个让我笨" in half


def test_user_attention_filters_the_screen_and_quiet_stays_quiet():
    from app.modules.glance.situation import read_steer

    assert read_steer("一起看") == (None, None)
    assert read_steer("看画面里面的那只猫")[0] == "那只猫"
    assert read_steer("关注字幕")[0] == "字幕"
    assert read_steer("多说点")[1] == "more"
    assert read_steer("不要说")[1] == "quiet"
    assert read_steer("不用关注了")[0] == ""

    sit = Situation()
    sit.ingest(_obs("类型：video\n标题：猫片\n原文：这只猫会开门\n变化：猫在开门"))
    sit.note_user("看画面里面的那只猫")
    sit.hold_until = 0
    missed = sit.ingest(_obs("类型：video\n标题：猫片\n原文：把东西给我放下\n变化：换了一句"))
    assert missed is None
    hit = sit.ingest(_obs("类型：video\n标题：猫片\n原文：小猫又去开门了\n变化：猫还在"))
    assert hit is not None
    assert "猫" in hit.summary
    sit.note_user("多说点")
    sit.hold_until = 0
    assert sit.talk == "more"
    again = sit.ingest(_obs("类型：video\n标题：猫片\n原文：猫把门锁上了\n变化：猫锁门"))
    assert again is not None
    sit.note_user("不要说")
    sit.hold_until = 0
    assert sit.talk == "quiet"
    assert sit.ingest(_obs("类型：video\n标题：猫片\n原文：猫又来了\n变化：猫")) is None
    assert "那只猫" in sit.blocks()
    assert "他让你先别说" in sit.blocks()

"""内置情境卡：今晚这场戏，不是舞台背景库。"""
from typing import Dict, List, Optional, TypedDict


class SceneCard(TypedDict, total=False):
    id: str
    title: str
    setting: str
    conflict: str
    opening: str
    cam: str
    intent: str
    background: str


def _c(id: str, title: str, setting: str, conflict: str, opening: str,
       cam: str, intent: str, background: str) -> SceneCard:
    return {
        "id": id, "title": title, "setting": setting, "conflict": conflict,
        "opening": opening, "cam": cam, "intent": intent, "background": background,
    }


CARDS: List[SceneCard] = [
    _c("rain-alley", "雨夜小巷",
       "窄巷刚下过雨，地面反光，她撑着伞等你。",
       "她好像有话要说，又故意不先开口。",
       "像已经等了一会儿，潮气、懒，不要念伞的诗。",
       "half", "look", "/backgrounds/bg_alley.png"),
    _c("after-fight", "刚吵完",
       "刚才为小事顶过两句，空气还没散。",
       "谁也不想先认错，但也不想真翻脸。",
       "别道歉稿，别装没事。带一点刺，再给台阶。",
       "bust", "tease", "/backgrounds/bg_bedroom.png"),
    _c("concert-wings", "公演侧台",
       "演唱会刚谢幕，侧台灯还热着。",
       "她还在余韵里，不想立刻被拉回日常闲聊。",
       "气还没平，说话短、带一点得意。",
       "threeQ", "tease", "/backgrounds/bg_concert.png"),
    _c("sakura-wait", "花树下",
       "庭院樱花正盛，风把瓣吹到肩上。",
       "她约你出来，却假装只是路过。",
       "轻松、近、不要导游介绍风景。",
       "half", "cute", "/backgrounds/bg_sakura.png"),
    _c("cyber-rooftop", "夜城天台",
       "霓虹在下面流，风有点硬。",
       "她把你叫上来，不是为了看风景。",
       "冷一点、短一点，像真的在风里说话。",
       "full", "look", "/backgrounds/bg_cyber.png"),
    _c("guofeng-night", "檐下夜谈",
       "廊下灯笼，远处有人声又听不清。",
       "她今晚不想跳，只想被人陪着坐一会儿。",
       "慢、近、不要古风朗诵。",
       "close", "think", "/backgrounds/bg_guofeng.png"),
    _c("snow-town", "雪夜归途",
       "小镇刚停雪，路灯晕成一团。",
       "她手冷，却偏要逞强说没事。",
       "声音放轻，像怕惊扰积雪。",
       "half", "comfort", "/backgrounds/bg_snow.png"),
    _c("cafe-late", "打烊前",
       "咖啡馆只剩你们，杯子已经空了。",
       "该走了，谁也不提下一句去哪。",
       "像聊到一半被打烊灯打断。",
       "bust", "talk", "/backgrounds/bg_cafe.png"),
    _c("starry", "极光底下",
       "天裂开一条绿光，两个人都有点话少。",
       "太好看了，普通寒暄会显得很假。",
       "别赞叹风景清单，说人。",
       "long", "look", "/backgrounds/bg_starry.png"),
    _c("library", "闭馆后",
       "图书馆灯一盏一盏灭，只留过道。",
       "她翻到一页想给你看，又觉得说出来会很蠢。",
       "压低音量，带一点秘密。",
       "close", "shy", "/backgrounds/bg_library.png"),
    _c("unfinished", "上次没说完",
       "你们中间断过一截，话题还挂着。",
       "她记得，不确定你还记不记得。",
       "直接从上次的情绪接，不要欢迎回来。",
       "half", "tease", ""),
    _c("dawn-wait", "天快亮了",
       "聊得太晚，窗外已经发灰。",
       "该睡了，她还想再赖一句。",
       "困、软、不要精神满满地打招呼。",
       "bust", "relax", "/backgrounds/bg_beach.png"),
    _c("flower-dusk", "黄昏花田",
       "风把花浪推过来，裙子沾了一点花粉。",
       "她想拉你走两步，又觉得太像约会。",
       "亮、近、不要念花名。",
       "half", "cute", "/backgrounds/bg_flower.png"),
    _c("forest-quiet", "林中停一下",
       "树把天挡住，脚步声比话响。",
       "她不是迷路，是想把人带离有信号的地方。",
       "轻、慢，不要探险口吻。",
       "bust", "think", "/backgrounds/bg_forest.png"),
    _c("lab-overtime", "灯还亮着",
       "实验室只剩排风扇，屏幕还醒着。",
       "她加班到这份上，不想被问累不累。",
       "干、短、带一点烦。",
       "bust", "talk", "/backgrounds/bg_lab.png"),
    _c("matsuri", "祭典回程",
       "烟花散了，耳边还在响，木屐踩得慢。",
       "她想把金鱼袋塞给你，又觉得太小孩。",
       "热、近、不要导游介绍摊位。",
       "half", "tease", "/backgrounds/bg_matsuri.png"),
    _c("palace-step", "殿前台阶",
       "石阶凉，远处鼓停了。",
       "她穿得太正式，说话反而别扭。",
       "收着声音，不要戏腔。",
       "full", "look", "/backgrounds/bg_palace.png"),
    _c("skycity", "云上走廊",
       "云从栏杆底下过，风把衣摆抬起来。",
       "高处让她话少，不是怕，是想听你先开口。",
       "轻、短，不要抒情朗诵。",
       "full", "look", "/backgrounds/bg_skycity.png"),
    _c("space-window", "舷窗这边",
       "舷窗外是黑的，舱内灯条很细。",
       "她把你叫到窗边，不是为了看星星。",
       "低、近，不要科普。",
       "close", "think", "/backgrounds/bg_space.png"),
    _c("underwater", "水下回廊",
       "光从顶上漏下来，气泡偶尔打在肩上。",
       "她在水里话更少，靠距离说话。",
       "慢、近，不要旅游腔。",
       "half", "look", "/backgrounds/bg_underwater.png"),
    _c("rehearsal", "练功房半夜",
       "镜子还开着，地胶上有未擦的粉。",
       "练完了，她不想被夸，想被看见累。",
       "喘匀了再开口，短，不要点评动作。",
       "threeQ", "relax", "/backgrounds/bg_concert.png"),
    _c("kitchen-late", "冰箱灯",
       "只开了冰箱，两个人站在光里翻剩菜。",
       "饿比情绪诚实，她借这个把人留下。",
       "家常、近、不要浪漫旁白。",
       "bust", "talk", "/backgrounds/bg_cafe.png"),
]


def get_card(scene_id: str) -> Optional[SceneCard]:
    for c in CARDS:
        if c["id"] == scene_id:
            return c
    return None


def find_by_background(url: str) -> Optional[SceneCard]:
    if not url:
        return None
    for c in CARDS:
        if (c.get("background") or "") == url:
            return c
    return None


def list_cards() -> List[Dict[str, str]]:
    return [dict(c) for c in CARDS]

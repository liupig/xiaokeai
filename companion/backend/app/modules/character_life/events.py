"""可枚举的人生事件和确定性的选取规则。"""
import re
from dataclasses import dataclass
from datetime import date
from hashlib import blake2s


@dataclass(frozen=True)
class Event:
    key: str
    lane: str
    fact: str
    trace: str
    tag: str = ""
    plan: str = ""
    endings: tuple[str, ...] = ()
    adult: bool = False
    follow_up_days: int = 2
    world: str = ""


EVENTS = (
    Event("night-route", "hobby", "今天跑步故意没计时，第一次在转弯处停下来看水面。", "旧路线旁另画了一个弯，写着「不计时」。", "running"),
    Event("slow-partner", "hobby", "有人问能不能一起跑，开口就说自己很慢。角色答应了，反倒有点怕露出自己也会喘的样子。", "路线被划短一截，终点还没定。", "running",
          "想再跑一回，看看自己能不能喜欢一条跑不快的路。",
          ("两人第二次跑得比第一次还慢，角色却把那条路线留了下来。", "对方没能赴约。角色照样跑完，把短路线留给以后想偷懒的自己。")),
    Event("wrong-song", "hobby", "在同一处反复弹错，后来单独弹了一遍那几个错音，居然舍不得擦掉。", "谱边保留了一段没被划掉的错音。", "music"),
    Event("margin-note", "hobby", "旧书前任读者在页角写了「不同意」。角色读回去三页，发现自己反而同意那个人。", "在「不同意」下面补了个小小的勾。", "reading"),
    Event("burnt-batch", "hobby", "第一份做糊了，本来要全扔，试了一口却先把最焦的角留给自己。", "食谱时间旁添了句「下次还是留个焦边」。", "cooking"),
    Event("apron-back", "work", "收工时发现围裙背面留了一个湿爪印。想擦，想了想又把围裙翻面挂起来。", "围裙背后只剩一个模糊的爪尖。", "pet_care", adult=True),
    Event("last-lesson", "work", "有人等大家都走了，才拿着一道几乎空白的题来问。角色把原本写好的讲解换成一个问题。", "纸背只写了一个问号。", "teaching"),
    Event("wrong-count", "work", "收尾时发现一笔小钱对不上。旁人说算了，角色重新核了一遍，原来是自己记重了一次。", "账页上有一行被单独圈起来的数字。", "retail", adult=True),
    Event("borrowed-bowl", "friends", "熟人还来借走很久的碗，里面放了两颗果子，提都没提自己忘过这件事。", "碗底多了两颗一大一小的果子。"),
    Event("wrong-gift", "friends", "熟人说上次送的东西其实拿反了。角色已经用顺手，决定先问问原本那件是什么。", "原来的包纸还压着，折痕的方向果然反了。", "",
          "等那人把真正想送的东西拿来，再决定要不要换回去。",
          ("原来的那件确实更合适，可拿反的那件已经有了位置，两人最后只换了包纸。", "对方拿来的东西太郑重，角色反而要求留下拿错的那件。")),
    Event("unmarked-door", "outing", "平常关着的侧门里传来练唱的声音，角色站了一会儿，没进去。", "折过的纸上新画了一扇门。", "",
          "下次路过再留一会儿。如果门开着，就问问能不能进去听一段。",
          ("侧门开着，里面只剩下收凳子的人。帮着收完才问到下次的时间。", "这次没有歌声，角色还是沿路走了一遍，把侧门留在了路线里。")),
    Event("one-seat", "outing", "去了平常不会去的地方，只剩一处很别扭的位置。坐下后才发现正好避开所有人在看的方向。", "座位边上刻着一个辨不清的字。"),
    Event("drawer-list", "private", "翻到一张旧清单。最想做的那件后来真的做了，自己却早忘了它当初那么难。", "末尾一项旁边有个很用力的勾。"),
    Event("second-cup", "private", "独处时下意识多拿了个杯子。把它收回去之前突然想到，已经很久没人在这个时候来过了。", "两个杯子并排摆了一会儿，最后收起一个。"),
    Event("unsent-thanks", "private", "想谢一个几乎不会再见的人，写下称呼就停住了，理由并没有自己以为的那么好说。", "称呼下面是一整行空白。", "",
          "先把纸折起来。过两天如果还想说，再把真正想谢的事写完。",
          ("那页纸最后没送出去。写完真正想谢的事以后，角色划掉了那个称呼。", "第二次动笔只写了两句，角色把纸送了出去，没等人回。")),
    Event("one-hour", "choice", "本来把空出来的时间让给了别人，临到头忽然改口，说自己也想留一会儿。", "那一格原先写了名字，后来只留一道划线。"),
    Event("different-use", "choice", "有件一直舍不得用的东西，今天正好用得上。先把它拿出来，没急着拆开。", "东西没拆，原来的位置倒空了。", "",
          "给自己两天想想：到底在等什么场合才肯用？",
          ("那件东西终于用掉了。真正舍不得的是拆开之前那种什么都可能发生的感觉。", "东西送给了更用得上的人，角色留下了原来的盒子。")),
    Event("try-another", "choice", "一个同行提到可以去看看另一种工作。角色先问了到时候要做的第一件小事，没有直接答应换行。", "纸上只记了一个时间，没有写承诺。", "career",
          "去做一回那件入门的小事。做完再说这究竟是想换行，还是想换个喘气的地方。",
          ("试过才发现喜欢的是其中一小段，打算先学下去，现有工作照常做。", "原先以为会喜欢，做过一回发现不合适。角色把约好的时间划掉了，倒省了继续猜。"), adult=True),
    Event("last-appointment", "work", "最后一位客人到了门口才承认自己记错了日子。角色把门再开了一会儿，只给对方找出下次的预约。", "预约簿边角留着刚被圈出来的下一格。", "pet_care", adult=True, world="everyday"),
    Event("extra-question", "work", "交回去的小测里夹着一张学生自己出的题。角色解了半天，发现题目的条件里故意藏了一个漏洞。", "答案栏只填了六个字：下回你来讲。", "teaching"),
    Event("window-team", "work", "改橱窗时想压下那块旧招牌，同事却坚持把自己第一次写错的那面留出来。", "玻璃另一边倒着的错字还看得见。", "retail", adult=True),
    Event("quiet-handover", "work", "交班前才发现同事悄悄给自己留了两分钟安静时间。角色没有再顺手接一件事，真坐完了这两分钟。", "值班休息区的杯垫被移到不用说话的位置。", "care_work", adult=True, world="everyday"),
    Event("after-shift-bowl", "work", "下班经过吃东西的地方，第一次选了平常总给别人留的那份。坐下来才想起来，今天不用赶着解释自己为什么晚到。", "桌上的纸单叠好，压在第二天要带的东西下面。", "care_work", adult=True, world="everyday"),
    Event("dawn-meal", "work", "下夜班时外面开始有人买早饭。角色想起家里留的晚饭，从摊子前经过，回去把那份菜分成了两顿。", "冰箱里那盒菜多了一张「醒了再吃」的纸条。", "night_shift", adult=True, world="everyday"),
    Event("daylight-errand", "choice", "原以为下夜班可以顺便办一件事，站在已经开门的店前却转身回家了。决定下回把这点力气算给自己。", "出门前揣好的单子原样折了回去。", "night_shift", adult=True, world="everyday"),
    Event("meal-swaps", "friends", "几次轮班都错过熟人的饭点，这回两人商量试试反过来约，自己的下班时间当对方的早饭。", "原先写好的晚饭时间被挪到了另一栏。", "night_shift",
          "等下一班换完，看看这顿谁的早饭先变成谁的晚饭。",
          ("早饭那家临时没开门。他们买了两份最容易带走的东西，在路边坐了一会儿。", "两边都准时到了，聊到一半才发现这顿饭把各自一天的开头和结尾接起来了。"),
          adult=True, follow_up_days=4, world="everyday"),
    Event("blank-diff", "work", "原本准备给同事解释一长串代码改动，看到对方先把复现过程写清楚，角色临时把评论删成了一句谢谢。", "写了三段的草稿里只剩最后一行。", "software", world="everyday"),
    Event("paper-not-pixel", "work", "把两版设计打印出来，纸上最显眼的地方偏偏是屏幕上一直没注意到的那一块。", "印出来的两张纸被折在不同的地方。", "creative_work", world="everyday"),
    Event("wrong-stop", "work", "到熟悉的路口时发现有个老顾客天天在那里等的那块阴凉没了。收工绕回去看，才知道天凉了，对方换到有光的地方。", "原来记住的地标旁又添了一处。", "transport", adult=True, world="everyday"),
    Event("two-bowls-back", "work", "忙完那一拨客人，有个同事把热的那碗端到自己面前。角色习惯性要让回去，话到嘴边改成了谢谢。", "备用碗还空着，没有再临时接一份。", "hospitality", world="everyday"),
    Event("sole-left", "work", "收工见一只还没配对的手套，角色原先以为是自己的。把两只摆在一块才发现磨破的地方刚好相反。", "手套在换衣处并排留着，谁拿走都能看见另一只。", "manual_work"),
    Event("soft-release", "work", "一位长期客户改了主意。角色先把草稿关了，第二次再打开，发现里面有一段单独留给自己也挺合适。", "那一页从交付稿挪到了私人草稿里。", "freelance", adult=True, world="everyday"),
    Event("no-year-group", "work", "同组的人都在讲结果。角色把没弄明白的地方圈了起来，等人散了才叫住一个也圈在同一处的人。", "两个圈并排留在各自的纸上。", "student"),
    Event("library-corner", "hobby", "本来要找安静的地方背东西，到了才发现自己最舍不得的是往常能听见别人在说话的桌角。", "划掉最安静的桌号，换回原来靠过道的位置。", "student"),
    Event("after-school-trade", "friends", "一个同学想用自己最拿手的东西换角色最不擅长的事。两人约定先各教一回，再决定值不值得换。", "纸被撕成两半，每人只拿对方写的一半。", "student",
          "约好先各教一次。角色有点想知道对方是不是也会怕讲错。",
          ("两边都没教完，却各留下了一种对方没想过的做法。", "对方承认自己其实也没有那么擅长。两人把第一次约课改成了一起练习。"),
          follow_up_days=3),
    Event("weekday-name", "private", "已经可以不用看工作日，今天还是照旧在那个点站起来。过了一会儿才想起，现在愿不愿意出门只需要问自己。", "老日历翻到这一页，背面什么安排也没写。", "retired"),
    Event("own-morning", "choice", "熟人又约了惯常见面的时段。角色第一次开口说想把那个早上留给自己，约了晚些再见。", "把时钟旁的见面时间往后挪了一格。", "retired"),
    Event("old-workbench", "friends", "旧同事来问一个以前总由角色拿主意的小问题，聊了一半，角色发现很想知道年轻人已经试过什么。", "送来求解的纸上多了一句「你先说」。", "retired"),
    Event("own-spoon", "private", "这些天总顺手把自己的那份留到最后，今天先给自己添了一勺。发现没有人因此少吃，倒是自己还不太习惯。", "自己的碗第一次提前摆在顺手的位置。", "caregiving"),
    Event("backup-afternoon", "choice", "有人主动说能替自己照看一阵。角色差点说不用，想了想只交代了真正需要交代的一件事。", "原本写了六行的交代纸只留下最上面一行。", "caregiving"),
    Event("box-under-chair", "private", "一个人住久了，收东西时开始记得按自己的习惯放。今天居然没有为了想象中的客人重新摆一遍。", "最常用的小东西终于放到了最顺手的位置。", "living_alone"),
    Event("two-shelves", "friends", "同住的人把共用架子空出一格，角色原以为是提醒自己收拾，后来才知道是在问要不要留给自己。", "架子上有一格只空着，没有贴谁的名字。", "shared_home"),
    Event("spare-key", "choice", "一起生活的人问要不要给常来的熟人留把钥匙。角色犹豫了半天，发现真正介意的是来之前有没有人说一声。", "多出来的那把钥匙还挂在原处。", "shared_home",
          "先谈清来之前怎么打招呼，再决定那把钥匙给不给。",
          ("两个人先约定来之前打声招呼。钥匙还是留在挂钩上，讨论反而轻松了。", "熟人自己说根本用不到钥匙。后来留下的是一条下次上门前会问的习惯。"),
          adult=True, follow_up_days=3),
    Event("first-club", "outing", "刚搬来还分不清哪条路叫近，误打误撞走进一个熟人都不来的地方，反而敢先开口问。", "回去给那条走错的路做了记号。", "new_arrival"),
    Event("midweek-table", "friends", "在新地方第二次碰见同一个人，才发现两人都把那张小桌当作临时找不到地方时的去处。", "桌角那一点擦不掉的划痕，这次一眼就认出来了。", "new_arrival"),
    Event("film-edge", "hobby", "重新看自己拍下来的东西，真正想留的那一张主体没拍全，却留下了旁边别人没注意的动作。", "给那一张圈了一下，位置在原先选中的照片之外。", "photography"),
    Event("small-sprout", "hobby", "总以为会养活那盆最用心照料的，偏偏是角落里那株先冒了个尖。角色没急着去动它。", "花盆边上留了一块小纸牌，暂时没写名字。", "gardening"),
    Event("missing-piece", "hobby", "修东西时找不到原件，翻出自己以前嫌丑留下的替代件，装上才发现它居然最好用。", "没有用上的原配件被单独放回盒里。", "handcraft"),
    Event("left-by-water", "outing", "走到水边才发现自己一直在赶一段没人规定的路。坐下来以后，原来想去的地方也没那么着急。", "那一段路在纸上被画成了一个很长的停顿。"),
    Event("inside-cover", "private", "拿起一件以为是自己的旧东西，才认出里面留着别人写的一小句提醒。看懂以后，也没有立刻还回去。", "封里有一句快磨没了的话，只有开头看得清。"),
    Event("tiny-no", "choice", "有人好意替角色定了一个看似省事的安排。角色开口说不时声音很轻，说完却松了口气。", "记下的是自己真正想去的时间，旧时间只划了一道。"),
    Event("other-stair", "outing", "那条每天都走的路有一截暂时过不去。拐到另一边时，角色第一次看见平常只是听见动静的那个地方。", "以后想起绕路也可以从这里开始。"),
    Event("half-apology", "friends", "熟人来的时候带了平常不会带的东西，看来是想道歉，却一直在讲别的。角色也没逼对方说完。", "两人真正谈到的只有袋子里那件小东西。"),
    Event("return-before-snow", "outing", "约好的地方比想象中安静，原先等的人也没来。角色只停到自己真的想走，就提前回去了。", "出发时带的东西一直没有从里面拿出来。"),
    Event("rune-margin", "hobby", "翻到旧术式的边注，发现前人在最难的那一步也写了一个问号。角色没有擦掉，反而把自己的问号画在旁边。", "两个时代的问号挨在一起。", "fantasy", world="other"),
    Event("lantern-promise", "outing", "听人说河对岸会留一盏灯给晚到的人，角色这次想亲眼辨认是哪一盏。", "把路记在叠过好几次的纸角。", "fantasy",
          "等下次天黑，沿着河边认一遍那盏灯。",
          ("过去才知道灯是给迷路回来的小船留的。角色跟着守灯人等完了那一趟。", "那边今天没有灯。返程时倒在自己这岸看见有人把灯移出来了一点。"),
          follow_up_days=4, world="other"),
)

# Each story has a hint the character can let slip and a fuller private memory.
_PRIVATE_STORIES = (
    ("running", "有一条路线从来不记配速。", "第一次认真想放弃跑步那天，绕着那条路走了一圈才回家。后来只要觉得自己跑得太慢，就去走那一圈。"),
    ("music", "有一段谱子从来不当着人弹。", "那几句旋律原本写给一个已经搬走的人。没有送出去的谱子后来改过好几回，每次都把第一行留成原样。"),
    ("reading", "有本旧书从不借人，书倒并不值钱。", "那本书的空白处留着以前写给未来自己的话。前阵子翻过一次，发现最不客气的那句意外地有用。"),
    ("", "会把看起来毫无用处的纸片夹好。", "曾想记住一段谁都不觉得值得记的日子，最后只留下几张纸。回头想起来，日期全忘了，反而记得第一张纸怎么折。"),
    ("", "有件旧东西收得仔细，却几乎没有拿出来过。", "它是第一次拒绝一件自己其实很想答应的事之后留下的。如今再碰到同样的选择，倒不一定还会做得一样。"),
)

_TAGS = {
    "running": r"跑步|夜跑|马拉松|jogging|running",
    "music": r"琵琶|钢琴|吉他|奏乐|作曲|音乐|piano|guitar|music",
    "reading": r"读书|看书|小说|旧书|reading|novels",
    "cooking": r"做饭|烘焙|厨师|甜点|cooking|baking|chef",
    "pet_care": r"宠物美容|宠物店|兽医|pet groom|veterinar",
    "teaching": r"教师|老师|讲师|教书|teacher|tutor",
    "retail": r"店员|店长|收银|掌柜|cashier|shopkeep",
    "career": r"转行|想开店|工作室|换工作|学徒|career change|studio",
    "care_work": r"护士|医护|护工|医生|护理员|nurse|physician|medical assistant",
    "night_shift": r"夜班|值夜|倒班|夜间值班|night shift|graveyard shift",
    "software": r"程序员|软件工程师|开发者|写代码|programmer|developer|software engineer",
    "creative_work": r"设计师|美术师|插画师|剪辑师|designer|illustrator|video editor",
    "transport": r"快递员|配送员|司机|送货员|courier|delivery driver|truck driver",
    "hospitality": r"服务员|后厨|餐饮|厨师|咖啡师|barista|waiter|chef",
    "manual_work": r"工人|工厂|维修工|焊工|技工|factory worker|mechanic|welder",
    "freelance": r"自由职业|接单|个体经营|freelanc|self-employed",
    "student": r"学生|读大学|在读|高中生|中学生|留学|student|undergraduate",
    "retired": r"退休|retired|retirement",
    "caregiving": r"照看(?:孩子|家人)|照护(?:老人|家人)|全职家长|带娃|caregiver|stay-at-home parent",
    "living_alone": r"独居|一个人住|lives? alone",
    "shared_home": r"同住|合租|室友|同居|roommate|housemate|lives? with",
    "new_arrival": r"刚搬|刚到|刚迁到|new in town|just moved",
    "photography": r"摄影|拍照|相机|photograph",
    "gardening": r"园艺|种花|种菜|养花|gardening|grow plants",
    "handcraft": r"手作|木工|编织|缝纫|crafting|woodwork|knitting|sewing",
    "fantasy": r"修仙|魔法世界|仙侠|古代|王国|星际|wizard|medieval|spacefaring",
}
_WORK_TAGS = frozenset({
    "pet_care", "teaching", "retail", "care_work", "software", "creative_work", "transport",
    "hospitality", "manual_work", "freelance", "student", "retired",
})
_DIGITS = "零一二三四五六七八九"


def card_age(card: str) -> int | None:
    years = re.search(r"(?<![0-9])([0-9]{1,3}) *(?:岁|years old)", card, re.I)
    if years:
        return int(years[1])
    years = re.search(r"(?<![零一二三四五六七八九十])([一二三四五六七八九]?十[一二三四五六七八九]?|[零一二三四五六七八九])岁", card)
    if not years:
        return None
    text = years[1]
    if "十" in text:
        tens, _, units = text.partition("十")
        return 10 * (_DIGITS.index(tens) if len(tens) == 1 else 1) + (_DIGITS.index(units) if len(units) == 1 else 0)
    return _DIGITS.index(text) if len(text) == 1 else None


def _index(value: str, size: int) -> int:
    return int.from_bytes(blake2s(value.encode(), digest_size=4).digest(), "big") % size


def profile(card: str, previous: dict) -> dict:
    occupation = previous.get("occupation") or ""
    source = occupation + " " + card
    age = previous.get("age")
    if age is None:
        age = card_age(card)
    stage = ("minor" if age < 18 else "adult") if type(age) is int else "unknown"
    gender = re.search(r"(?:性别 *[：:]|gender *:) *(女|男|非二元|female|male|nonbinary)", card, re.I)
    tags = [tag for tag, pattern in _TAGS.items() if re.search(pattern, source, re.I)]
    if occupation:
        for work_tag in _WORK_TAGS:
            if work_tag in tags and not re.search(_TAGS[work_tag], occupation, re.I):
                tags.remove(work_tag)
    return {"stage": stage, "gender": gender[1] if gender else None,
            "world": "other" if "fantasy" in tags else "everyday", "tags": tags}


def select_event(character_id: int, day: date, traits: dict, recent: list[str]) -> Event:
    candidates = [
        event for event in EVENTS
        if (not event.adult or traits["stage"] == "adult")
        and (not event.tag or event.tag in traits["tags"])
        and (not event.world or event.world == traits["world"])
        and (event.key != "apron-back" or traits["world"] == "everyday")
    ]
    available = [event for event in candidates if event.key not in recent]
    if not available:
        return min(candidates, key=lambda event: recent.index(event.key))
    lane = ("hobby", "friends", "outing", "private", "choice", "work")[day.toordinal() % 6]
    chosen = [event for event in available if event.lane == lane]
    if not chosen:
        chosen = [event for event in available if event.lane != "work"] or available
    return chosen[_index(f"{character_id}/{day.isoformat()}", len(chosen))]


def ending(event_key: str, character_id: int, day: date) -> str:
    event = next((item for item in EVENTS if item.key == event_key), None)
    if not event or not event.endings:
        return ""
    return event.endings[_index(f"{character_id}/{day.isoformat()}/{event_key}", len(event.endings))]


def private_story(character_id: int, traits: dict, card: str) -> tuple[str, str] | None:
    if re.search(r"小秘密|秘密[：:]|secret[ :]", card, re.I):
        return None
    matched = [item for item in _PRIVATE_STORIES if item[0] in traits["tags"]]
    candidates = matched or [item for item in _PRIVATE_STORIES if not item[0]]
    _, hint, story = candidates[_index(str(character_id), len(candidates))]
    return hint, story


_CONTACT_LABELS = {
    "running": ("跑友", "running partner"),
    "friends": ("朋友", "好友", "friend"),
    "work": ("同事", "colleague"),
    "student": ("同学", "classmate"),
    "shared_home": ("室友", "roommate"),
}


def contacts(card: str) -> dict[str, str]:
    result = {}
    for role, labels in _CONTACT_LABELS.items():
        pattern = "|".join(labels)
        # Use named contacts from the card. Unnamed relationships stay unnamed.
        match = re.search(fr"(?:{pattern})\s*[：:「“]\s*([^\n，。；、」”]{{1,24}})", card, re.I)
        if match:
            value = match[1].strip()
            if re.fullmatch(r"[\u4e00-\u9fff]{1,5}|[A-Za-z][A-Za-z .'-]{0,22}", value):
                result[role] = value
                continue
        match = re.search(fr"(?:{pattern})(阿[\u4e00-\u9fff])", card)
        if match:
            result[role] = match[1]
    return result


def event_contact(event: Event, cast: dict[str, str]) -> str:
    if event.tag in {"running", "student", "shared_home"}:
        return cast.get(event.tag, "")
    if event.lane in {"work", "friends"}:
        return cast.get(event.lane, "")
    return ""


def card_occupation(card: str) -> str:
    for tag, pattern in _TAGS.items():
        if tag in _WORK_TAGS and (match := re.search(pattern, card, re.I)):
            return match[0]
    return ""

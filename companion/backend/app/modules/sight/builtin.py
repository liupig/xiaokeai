"""五类体验的阶段和陪伴。每一段都是固定格子，不靠临场再编一套。"""
from __future__ import annotations

from .model import Kind, Phase, Sub


def _phase(pid: str, label: str, say: str, speak: str, company: str, slots: tuple[str, ...] = (), frames: int = 1, detail: bool = False, ahead: tuple[str, ...] = (), mark: str = "", look: bool = False, ask: str = "") -> Phase:
    return Phase(pid, label, frames, detail, slots, say, speak, company, ahead, mark, look, ask)


def _sub(kind: Kind, sid: str, label: str, *, match: str, scene: str = "", names: tuple[str, ...] = (), processes: tuple[str, ...] = (), titles: tuple[str, ...] = (), process_phase: dict[str, str] | None = None, phases: tuple[Phase, ...] = ()) -> Sub:
    return Sub(
        id=sid,
        label=label,
        kind=kind.id,
        scene=scene or kind.scene,
        match=match,
        names=names,
        processes=tuple(item.lower() for item in processes),
        titles=titles,
        process_phase=process_phase or {},
        phases=phases or kind.template,
    )


def kinds() -> tuple[Kind, ...]:
    return (_game(), _music(), _movie(), _video(), _work())


def _game() -> Kind:
    template = (
        _phase("launch", "正在打开", "游戏正在打开", "还没进游戏。不要编菜单和局面。", "等他进游戏。只说正在打开，不介绍玩法。"),
        _phase("menu", "菜单", "现在在游戏菜单", "只说停在菜单。不要编局内操作。", "菜单里少说话。他在选什么看清了再接一句。"),
        _phase("playing", "游戏中", "现在在游戏里。局面：{state}", "局面空着就不要编操作和输赢。", "只接看见的局面。不指挥走位和技能。", ("state",)),
    )
    kind = Kind("game", "玩游戏", "game", True, 8, template, ())
    subs = (
        _league(kind),
        _dnf(kind),
        _cf(kind),
        _cs2(kind),
        _dota(kind),
        _elden(kind),
        _fortnite(kind),
        *_region_games(kind),
    )
    return Kind(kind.id, kind.label, kind.scene, kind.configurable, kind.interval, kind.template, subs)


def _league(kind: Kind) -> Sub:
    phases = (
        _phase("launch", "正在打开", "英雄联盟正在打开", "还没进客户端。不要编大厅和英雄。", "等客户端起来。不提段位，不催他开排位。", ahead=("lobby",), mark="只有启动画面或转圈，还没有主页"),
        _phase("lobby", "大厅", "现在在英雄联盟大厅。模式：{mode}", "模式空着就不要猜他要打排位还是匹配。", "大厅里陪他挑。看清是匹配、排位、大乱斗或人机，就接一句你的看法。不替他点开始。", ("mode",), ahead=("party", "queue", "select"), mark="有主页、PLAY 或模式入口，没有一圈英雄头像"),
        _phase("party", "组队", "现在在组队。模式：{mode}", "没看清房间就不要编队友和位置。", "房间里一起等。有人进来可以提一句。位置空着不要替他锁上路或打野。", ("mode", "lane"), ahead=("queue",), mark="房间里有队友格子和邀请"),
        _phase("queue", "排队", "正在排队等对局", "还在排队。不要编匹配到了。", "排队就安安静静陪着。不猜还要多久，不催他退。", ahead=("select",), mark="写着正在寻找对局，或弹出接受对局"),
        _phase("select", "选英雄", "现在在选英雄。英雄：{hero}。分路：{lane}", "英雄名字空着就不要点评具体英雄，也不要替他锁定。", "他在选人。名字看清了，用一两句说这个英雄好不好玩、你喜不喜欢看他用。不报连招，不报出装顺序。", ("hero", "lane"), detail=True, ahead=("load",), mark="标题写着选择你的英雄，中间是一圈或一排可以点的英雄头像"),
        _phase("load", "进入对局", "正在进入对局。英雄：{hero}", "英雄名字空着就不要猜是谁。", "加载时如果看清了他这局的英雄，就叫出名字，说你跟他进这局。不替他规划出门装。", ("hero",), frames=2, ahead=("shop", "leave", "lane"), mark="双方英雄的大立绘卡片，没有选择你的英雄，也没有小地图和血条", look=True),
        _phase("shop", "出装", "现在在泉水里出装。英雄：{hero}。装备：{items}", "这一眼未确认购买结果。没读到装备名称不等于没买，不要说装备栏为空。", "他打开了商店。只点评确实已买的装备，打开、推荐、悬停都不等于购买。不指挥下一件。", ("hero", "items"), detail=True, ahead=("leave", "lane"), mark="左边商店格子打开了"),
        _phase("leave", "出门", "现在准备出门。英雄：{hero}。分路：{lane}", "分路空着就不要指定他去哪条路。", "要出门了。叫得出英雄就叫。分路看清了提一句就好，不喊贴墙，不喊交技能。", ("hero", "lane"), ahead=("lane",), mark="人在泉水上，商店没打开，"),
        _phase("lane", "局内", "现在在对线。英雄：{hero}。线路：{lane}。局面：{state}", "未确认的身份、线路和局面不要补全。未确认不等于不存在。", "坐在旁边看他打。叫得出英雄就叫名字。引号里有新动作就接那一句，像一起开黑。不指挥探草、支援或交技能。", ("hero", "lane", "state"), frames=4, ahead=("fight", "dead", "score"), mark="旁边有一排小兵"),
        _phase("fight", "团战", "现在在打团。英雄：{hero}。局面：{state}", "局面空着就不要编谁开团、谁收割。", "打起来了就短句。叫英雄的名字，接看见的交火。不喊他交闪现或大招。", ("hero", "state"), frames=4, ahead=("lane", "dead", "score"), mark="团战，或好几个英雄贴在一起放技能"),
        _phase("dead", "阵亡", "现在阵亡了，在等复活。英雄：{hero}", "不要编是谁杀掉的，也不要责怪。", "他倒了就叫名字，轻轻接一句。引号里有复活秒数就报秒数。不复盘，不骂操作。", ("hero",), ahead=("lane", "score"), mark="画面变灰，或写着返回于、等待复活"),
        _phase("score", "结算", "对局已经结束。英雄：{hero}。结果：{result}", "结果空着就不要编胜负、KDA 和胜点。", "这局结束了。叫英雄的名字，赢了一起高兴，输了一起叹气。不编数据和胜点。", ("hero", "result"), detail=True, ahead=("lobby",), mark="出现胜利或失败的结算面板"),
    )
    return _sub(
        kind, "league", "英雄联盟", match="process",
        names=("英雄联盟", "lol", "league of legends", "リーグ・オブ・レジェンド", "리그 오브 레전드", "롤"),
        processes=("leagueclient.exe", "leagueclientux.exe", "league of legends.exe"),
        process_phase={
            "leagueclient.exe": "lobby",
            "leagueclientux.exe": "lobby",
            "league of legends.exe": "load",
        },
        phases=phases,
    )


def _dnf(kind: Kind) -> Sub:
    phases = (
        _phase("launch", "正在打开", "地下城与勇士正在打开", "还在登录或选服。不要编角色和副本。", "等他选服。不催，不编频道。"),
        _phase("role", "选角色", "正在选角色", "角色名字空着就不要叫错职业。", "选角时可以问今天用谁，看不清职业就不要猜。"),
        _phase("room", "赛丽亚房间", "现在在赛丽亚的房间", "还在房间里。不要编已经进了副本。", "房间是出发前。陪他整理，不替他接任务，不编疲劳。"),
        _phase("town", "城镇", "现在在城镇。地点：{place}", "地点空着就不要编在哪个城镇。", "城镇里他在走路或找人。看清地名再接，不指路。", ("place",)),
        _phase("gate", "选副本", "正在选副本。副本：{place}", "副本名字空着就不要编难度。", "选本时只接看见的副本名。不替他调难度，不催他进图。", ("place",), detail=True),
        _phase("clear", "清图", "正在清副本里的房间。局面：{state}", "局面空着就不要编掉落和连招。", "清图时短句跟着房间走。不指挥技能键，不编爆装。", ("state",)),
        _phase("boss", "首领", "正在打首领。首领：{boss}", "首领名字空着就不要编机制。", "打首领时陪着紧张。名字看清了可以叫出来，不教躲技能。", ("boss",)),
        _phase("result", "结算", "副本结束了，正在结算。结果：{result}", "结果空着就不要编评价和翻牌。", "结算和翻牌时把看见的结果说出来。不编出了什么装备。", ("result",), detail=True),
        _phase("loot", "处理装备", "正在处理掉落。装备：{items}", "装备空着就不要编该留还是该分解。", "他在看装备。只念看见的名字，不替他决定卖还是穿。", ("items",), detail=True),
    )
    return _sub(kind, "dnf", "地下城与勇士", match="process", names=("地下城与勇士", "dnf", "던전앤파이터", "던파", "アラド戦記", "dungeon fighter", "dungeon & fighter"), processes=("dnf.exe",), phases=phases)


def _cf(kind: Kind) -> Sub:
    phases = (
        _phase("launch", "正在打开", "穿越火线正在打开", "还没进大厅。不要编模式和房间。", "等大厅。不提商城，不催他买枪。"),
        _phase("lobby", "大厅", "现在在穿越火线大厅。模式：{mode}", "模式空着就不要猜团队、爆破还是生化。", "大厅里陪他挑模式。看清模式名再接，不替他进房。", ("mode",)),
        _phase("room", "房间", "现在在房间里等开始。模式：{mode}。地图：{map}", "地图或模式空着就不要编。", "房间里等房主。可以轻轻说在等，不指挥阵营。", ("mode", "map")),
        _phase("buy", "购买", "这一回合在买武器。武器：{weapon}", "武器空着就不要编该买什么。", "买枪时间只接看见的枪名。不推荐，不提充值。", ("weapon",), detail=True),
        _phase("round", "对局", "正在对局里。模式：{mode}。局面：{state}", "局面空着就不要编残局和包点。", "枪战里短句。爆破只在看见包或拆包时提，不指挥站位。", ("mode", "state")),
        _phase("result", "结算", "这一局结束了。结果：{result}", "结果空着就不要编比分。", "结算时接看见的胜负。不念战绩表，不怪枪法。", ("result",), detail=True),
    )
    return _sub(kind, "cf", "穿越火线", match="process", names=("穿越火线", "cf", "crossfire", "크로스파이어"), processes=("crossfire.exe",), phases=phases)


def _cs2(kind: Kind) -> Sub:
    phases = (
        _phase("menu", "主菜单", "现在在 CS2 主菜单", "还在菜单。不要编已经匹配到了。", "菜单里少说话。他在找比赛或开练习，看清了再接。"),
        _phase("lobby", "组队", "正在组队等比赛。模式：{mode}", "模式空着就不要猜竞技还是休闲。", "等队友或排队。不催他开麦，不编地图。", ("mode",)),
        _phase("warmup", "热身", "正在热身。地图：{map}", "地图空着就不要编在哪张图。", "热身可以轻轻说地图。不指挥练枪点。", ("map",)),
        _phase("buy", "购买", "冻结时间，正在买枪。武器：{weapon}。阵营：{side}", "武器或阵营空着就不要编该存钱还是该买。", "买枪阶段只接看见的钱和枪。不替他决定全起或存钱。", ("weapon", "side"), detail=True),
        _phase("round", "回合", "回合开始了。阵营：{side}。局面：{state}", "局面空着就不要编包点、残局和道具。", "回合里短句跟着看见的交火。不喊扔闪，不报点位。", ("side", "state")),
        _phase("dead", "观战", "这一回合已经倒下，正在观战", "不要编是谁打掉的。", "观战就安静看着剩下的人。不指挥存活的队友。"),
        _phase("score", "计分", "比赛停在计分板。结果：{result}", "比分空着就不要编上下半场。", "计分时只说看见的比分。不预测能不能翻。", ("result",), detail=True),
    )
    return _sub(kind, "cs2", "Counter-Strike 2", match="process", names=("counter-strike 2", "cs2", "cs", "反恐精英", "カウンターストライク", "카운터스트라이크"), processes=("cs2.exe",), phases=phases)


def _dota(kind: Kind) -> Sub:
    phases = (
        _phase("menu", "主菜单", "现在在刀塔主菜单", "还没进比赛。不要编分段。", "菜单里等他点开始。不比较他和英雄联盟的习惯。"),
        _phase("party", "组队", "正在组队。模式：{mode}", "模式空着就不要猜天梯还是普通。", "组队时少说话。模式看清了再接。", ("mode",)),
        _phase("pick", "选英雄", "正在选英雄。英雄：{hero}", "英雄空着就不要点评这个英雄。", "选人时英雄看清了可以说好不好玩。不报技能加点，不报出门装。", ("hero",), detail=True),
        _phase("strategy", "策略时间", "选人结束，正在策略时间。英雄：{hero}。分路：{lane}", "分路空着就不要指定他去哪路。", "策略时间可以轻轻问分路。看不清就别安排。", ("hero", "lane")),
        _phase("lane", "对线", "现在在对线。线路：{lane}。局面：{state}", "线路或局面空着就不要编补刀和压制。", "对线只接看见的线路和局面。不指挥拉野、不报眼位。", ("lane", "state")),
        _phase("mid", "中期", "对线过去了，现在在中期游走。局面：{state}", "局面空着就不要编推进还是打肉山。", "中期跟着他走。只接看见的带线和团，不替他做决定。", ("state",)),
        _phase("fight", "团战", "现在在打团。局面：{state}", "局面空着就不要编大招和买活。", "团战时短句。不喊交技能，不提买活。", ("state",)),
        _phase("score", "结算", "这场刀塔结束了。结果：{result}", "结果空着就不要编胜负和 KDA。", "结算时接看见的结果。不复盘整场。", ("result",), detail=True),
    )
    return _sub(kind, "dota2", "Dota 2", match="process", names=("dota 2", "dota2", "刀塔", "ドータ", "도타"), processes=("dota2.exe",), phases=phases)


def _elden(kind: Kind) -> Sub:
    phases = (
        _phase("menu", "标题", "现在在艾尔登法环的标题或读档", "还没进交界地。不要编进度。", "标题画面等他读档。不剧透后面的王。"),
        _phase("grace", "赐福", "停在赐福旁边。地点：{place}", "地点空着就不要编在哪张地图。", "赐福是休息。可以轻轻说歇一下，不催他升级，不编卢恩够不够。", ("place",)),
        _phase("level", "升级", "正在赐福里升级。卢恩：{runes}", "卢恩空着就不要编加点。", "他在加属性。只接看见的项目，不替他选力量或智力。", ("runes",), detail=True),
        _phase("roam", "探索", "正在交界地里走。地点：{place}。局面：{state}", "地点或局面空着就不要编下一处。", "探索时像跟着散步。看见地名再说，不指路，不剧透。", ("place", "state")),
        _phase("fight", "战斗", "正在和敌人打。局面：{state}", "局面空着就不要编该翻滚还是该喝药。", "战斗里短句。不指挥操作，不怪他贪刀。", ("state",)),
        _phase("boss", "首领", "正在打首领。首领：{boss}。局面：{state}", "首领名字空着就不要编机制。", "首领战陪着紧张。名字看清了可以叫。不教躲招。", ("boss", "state")),
        _phase("dead", "死亡", "刚刚倒下，卢恩掉在原地", "不要编卢恩还在不在，也不要责怪。", "死后轻轻说。不催他立刻捡，不提失去了多少。"),
    )
    return _sub(kind, "elden", "Elden Ring", match="process", names=("elden ring", "艾尔登法环", "エルデンリング", "엘든 링"), processes=("eldenring.exe",), phases=phases)


def _fortnite(kind: Kind) -> Sub:
    phases = (
        _phase("lobby", "大厅", "现在在堡垒之夜大厅。模式：{mode}", "模式空着就不要猜是否零建筑。", "大厅里等他选模式。不催他跳进去。", ("mode",)),
        _phase("island", "出生岛", "在出生岛等战车", "还没起飞。不要编落点。", "等战车的时候可以闲聊。不替他选落点。"),
        _phase("bus", "战车", "正在战车上。地点：{place}", "地点空着就不要编该在哪跳。", "战车上只接看见的地名。不替他喊跳。", ("place",)),
        _phase("drop", "跳伞", "正在跳伞落向。地点：{place}", "地点空着就不要编城镇名。", "跳伞时跟着他的落点说。看不清地名就只说在落。", ("place",)),
        _phase("loot", "搜刮", "落地在搜装备。地点：{place}。武器：{weapon}", "武器空着就不要编品质和该捡什么。", "搜刮时念看见的枪。不安排路线，不提圈。", ("place", "weapon")),
        _phase("storm", "缩圈", "安全区在动。局面：{state}", "局面空着就不要编圈在哪边。", "缩圈时只接看见的安全区。不指挥他往哪跑。", ("state",)),
        _phase("fight", "交火", "正在和其他人打。局面：{state}", "局面空着就不要编谁先开枪。", "交火短句。不喊盖楼，不喊该不该硬打。", ("state",)),
        _phase("end", "结算", "这一局结束了。结果：{result}", "结果空着就不要编胜利或第几名。", "结束了就陪他说。胜利或淘汰看清了再接，不编击杀数。", ("result",), detail=True),
    )
    return _sub(
        kind, "fortnite", "Fortnite", match="process",
        names=("fortnite", "堡垒之夜", "フォートナイト", "포트나이트"),
        processes=("fortniteclient-win64-shipping.exe",),
        phases=phases,
    )


def _region_games(kind: Kind) -> tuple[Sub, ...]:
    valorant = (
        _phase("menu", "主菜单", "现在在无畏契约的主菜单", "还没进对局。不要编特工和比分。", "菜单里等他找比赛。不催他开排位。"),
        _phase("lobby", "组队", "正在组队。模式：{mode}", "模式空着就不要猜。", "等队友的时候少说话。模式看清了再接。", ("mode",)),
        _phase("select", "选特工", "正在选特工。英雄：{hero}", "名字空着就不要点评这个特工。", "选特工时名字看清了可以说一句。不报技能，不替他锁定。", ("hero",), detail=True),
        _phase("buy", "购买", "这一回合在买枪。武器：{weapon}。阵营：{side}", "武器或阵营空着就不要编该买什么。", "购买阶段只接看见的枪。不替他存钱或全起。", ("weapon", "side"), detail=True),
        _phase("round", "回合", "回合开始了。阵营：{side}。局面：{state}", "局面空着就不要编包点。", "回合里短句跟着交火。不喊技能，不报点位。", ("side", "state")),
        _phase("dead", "观战", "这一回合已经倒下，正在观战", "不要编是谁打掉的。", "观战就安静看着。不指挥还活着的队友。"),
        _phase("score", "结算", "这一局结束了。结果：{result}", "比分空着就不要编胜负。", "结算时只接看见的结果。不复盘枪法。", ("result",), detail=True),
    )
    apex = (
        _phase("lobby", "大厅", "现在在 Apex 大厅。模式：{mode}", "模式空着就不要猜排位还是匹配。", "大厅里等他选模式。不催他跳进去。", ("mode",)),
        _phase("select", "选传奇", "正在选传奇。英雄：{hero}", "名字空着就不要点评这个传奇。", "选传奇时名字看清了接一句。不报技能组合。", ("hero",), detail=True),
        _phase("drop", "跳伞", "正在跳伞。地点：{place}", "地点空着就不要编落点。", "跳伞时跟着看见的地名说。看不清就只说在落。", ("place",)),
        _phase("loot", "搜刮", "落地在捡装备。地点：{place}。武器：{weapon}", "武器空着就不要编该捡什么。", "搜刮时念看见的枪。不安排路线。", ("place", "weapon")),
        _phase("fight", "交火", "正在交火。局面：{state}", "局面空着就不要编该不该打。", "交火短句。不喊走位，不指挥技能。", ("state",)),
        _phase("end", "结算", "这一局结束了。结果：{result}", "结果空着就不要编冠军或第几名。", "结束了再接看见的结果。不编击杀数。", ("result",), detail=True),
    )
    pubg = (
        _phase("lobby", "大厅", "现在在 PUBG 大厅。模式：{mode}", "模式空着就不要猜几排。", "大厅里等他进局。不替他选地图。", ("mode",)),
        _phase("plane", "航线", "正在飞机上。地点：{place}", "地点空着就不要编该在哪跳。", "航线上只接看见的地名。不替他喊跳。", ("place",)),
        _phase("drop", "跳伞", "正在跳伞。地点：{place}", "地点空着就不要编城镇名。", "跳伞时跟着落点说。看不清地名就只说在落。", ("place",)),
        _phase("loot", "搜刮", "落地在搜房子。地点：{place}。武器：{weapon}", "武器空着就不要编配件。", "搜刮时念看见的枪。不安排跑圈路线。", ("place", "weapon")),
        _phase("zone", "缩圈", "安全区在动。局面：{state}", "局面空着就不要编圈在哪边。", "缩圈时只接看见的安全区。不指挥他往哪跑。", ("state",)),
        _phase("fight", "交火", "正在交火。局面：{state}", "局面空着就不要编谁先开枪。", "交火短句。不喊趴下或冲。", ("state",)),
        _phase("end", "结算", "这一局结束了。结果：{result}", "结果空着就不要编名次。", "结束了再接看见的名次。不编击杀。", ("result",), detail=True),
    )
    overwatch = (
        _phase("menu", "主菜单", "现在在守望先锋的主菜单", "还没进对局。不要编英雄。", "菜单里少说话。他在找比赛，看清了再接。"),
        _phase("select", "选英雄", "正在选英雄。英雄：{hero}", "英雄空着就不要点评。", "选英雄时名字看清了接一句。不报技能，不替他锁定。", ("hero",), detail=True),
        _phase("round", "对局", "对局正在进行。局面：{state}", "局面空着就不要编推车或占点。", "对局里短句跟着看见的交火。不指挥技能。", ("state",)),
        _phase("score", "结算", "这一局结束了。结果：{result}", "结果空着就不要编胜负。", "结算时接看见的结果。不复盘阵容。", ("result",), detail=True),
    )
    genshin = (
        _phase("menu", "标题", "现在在原神的标题或登录", "还没进世界。不要编任务。", "标题画面等他进游戏。不剧透任务。"),
        _phase("world", "世界", "正在开放世界里走。地点：{place}。局面：{state}", "地点或局面空着就不要编下一处。", "探索时像跟着散步。看见地名再说，不指路，不剧透。", ("place", "state")),
        _phase("talk", "对话", "正在和人对话。这一句：{line}", "这一句空着就不要编剧情。", "对话时接看见的一句。不剧透后面，不替他做选项。", ("line",)),
        _phase("fight", "战斗", "正在战斗。局面：{state}", "局面空着就不要编该用什么技能。", "战斗里短句。不指挥操作。", ("state",)),
        _phase("domain", "秘境", "正在秘境或副本里。地点：{place}。局面：{state}", "地点空着就不要编机制。", "秘境里跟着这一间走。不教配队，不剧透奖励。", ("place", "state")),
    )
    maple = (
        _phase("login", "选频道", "正在登录或选频道", "还没进村庄。不要编地图。", "选频道时等他进去。不催。"),
        _phase("town", "村庄", "现在在村庄。地点：{place}", "地点空着就不要编在哪张图。", "村庄里他在准备。看清地名再接，不指路。", ("place",)),
        _phase("hunt", "练级", "正在地图里打怪。地点：{place}。局面：{state}", "地点或局面空着就不要编掉落。", "练级时短句跟着。不指挥技能键，不编经验。", ("place", "state")),
        _phase("boss", "首领", "正在打首领。首领：{boss}", "首领名字空着就不要编机制。", "首领战陪着紧张。名字看清了可以叫。不教躲招。", ("boss",)),
        _phase("result", "结算", "打完了。结果：{result}", "结果空着就不要编奖励。", "结算时只接看见的结果。不编掉了什么。", ("result",), detail=True),
    )
    lostark = (
        _phase("role", "选角色", "正在选角色", "角色空着就不要叫错职业。", "选角时可以问今天用谁。看不清职业就不要猜。"),
        _phase("town", "城镇", "现在在城镇。地点：{place}", "地点空着就不要编在哪座城。", "城镇里他在准备。看清地名再接，不替他接每日。", ("place",)),
        _phase("run", "副本", "正在清副本。地点：{place}。局面：{state}", "局面空着就不要编机制。", "清本时短句跟着房间。不指挥技能。", ("place", "state")),
        _phase("boss", "首领", "正在打首领。首领：{boss}", "首领名字空着就不要编机制。", "首领战只叫看见的名字。不教躲招。", ("boss",)),
        _phase("result", "结算", "副本结束了。结果：{result}", "结果空着就不要编奖励。", "结算时接看见的结果。不编出了什么。", ("result",), detail=True),
    )
    ffxiv = (
        _phase("login", "登录", "正在登录最终幻想14", "还没进游戏。不要编任务。", "登录时等他选角色。不催。"),
        _phase("city", "主城", "现在在主城。地点：{place}", "地点空着就不要编在哪座城。", "主城里他在走路或找人。看清地名再接，不指路。", ("place",)),
        _phase("duty", "任务", "正在做任务。地点：{place}。局面：{state}", "地点或局面空着就不要编任务内容。", "任务里跟着看见的这一步。不剧透后面的剧情。", ("place", "state")),
        _phase("fight", "战斗", "正在战斗。局面：{state}", "局面空着就不要编技能循环。", "战斗里短句。不指挥输出循环。", ("state",)),
        _phase("cut", "过场", "正在看过场。这一句：{line}", "这一句空着就不要编剧情。", "过场时接看见的一句。不剧透，不把角色说成他。", ("line",)),
        _phase("result", "结算", "副本结束了。结果：{result}", "结果空着就不要编奖励。", "结算时接看见的结果。不复盘。", ("result",), detail=True),
    )
    roblox = (
        _phase("home", "首页", "正在 Roblox 首页找体验", "还没进体验。不要编里面在玩什么。", "首页里他在挑。看清名字再接，不替他点进去。"),
        _phase("playing", "体验中", "正在一个 Roblox 体验里。标题：{title}。局面：{state}", "标题或局面空着就不要编规则。", "进了体验就按看见的局面陪。不假装知道这张地图的规则。", ("title", "state")),
    )
    hunter = (
        _phase("hub", "据点", "现在在据点里。地点：{place}", "地点空着就不要编要去哪。", "据点是出发前。陪他准备，不替他接任务。", ("place",)),
        _phase("board", "任务板", "正在任务板前。地点：{place}", "任务空着就不要编目标。", "看任务时只接看见的名字。不替他选择难度。", ("place",), detail=True),
        _phase("hunt", "狩猎", "正在狩猎。首领：{boss}。局面：{state}", "首领或局面空着就不要编。", "狩猎时跟着他。名字看清了可以叫，不教部位，不指挥翻滚。", ("boss", "state")),
        _phase("carve", "剥取", "狩猎结束，正在剥取。结果：{result}", "结果空着就不要编素材。", "剥取时只接看见的字。不编掉了什么。", ("result",), detail=True),
    )
    palworld = (
        _phase("menu", "菜单", "现在在幻兽帕鲁的菜单", "还没进世界。不要编帕鲁。", "菜单里等他进档。不剧透。"),
        _phase("base", "据点", "现在在据点。局面：{state}", "局面空着就不要编该造什么。", "据点里他在打理。只接看见的，不替他安排工作。", ("state",)),
        _phase("roam", "探索", "正在外面走。地点：{place}。局面：{state}", "地点或局面空着就不要编下一处。", "探索时跟着。看见地名再说，不指路。", ("place", "state")),
        _phase("fight", "战斗", "正在战斗。局面：{state}", "局面空着就不要编该抓还是该打。", "战斗里短句。不指挥捕捉。", ("state",)),
    )
    return (
        _sub(kind, "valorant", "无畏契约", match="process", names=("无畏契约", "valorant", "ヴァロラント", "발로란트"), processes=("valorant-win64-shipping.exe",), phases=valorant),
        _sub(kind, "apex", "Apex Legends", match="process", names=("apex legends", "apex", "エーペックス", "에이펙스"), processes=("r5apex.exe",), phases=apex),
        _sub(kind, "pubg", "PUBG", match="process", names=("pubg", "绝地求生", "배틀그라운드", "배그", "バトルグラウンド"), processes=("tslgame.exe",), phases=pubg),
        _sub(kind, "overwatch", "守望先锋", match="process", names=("守望先锋", "overwatch", "オーバーウォッチ", "오버워치"), processes=("overwatch.exe",), phases=overwatch),
        _sub(kind, "genshin", "原神", match="process", names=("原神", "genshin", "genshin impact", "원신"), processes=("genshinimpact.exe", "yuanshen.exe"), phases=genshin),
        _sub(kind, "maple", "冒险岛", match="process", names=("冒险岛", "maplestory", "메이플스토리", "メイプルストーリー"), processes=("maplestory.exe",), phases=maple),
        _sub(kind, "lostark", "失落的方舟", match="process", names=("失落的方舟", "lost ark", "로스트아크", "ロストアーク"), processes=("lostark.exe",), phases=lostark),
        _sub(kind, "ffxiv", "最终幻想14", match="process", names=("最终幻想14", "final fantasy xiv", "ffxiv", "ファイナルファンタジー14", "파이널판타지14"), processes=("ffxiv_dx11.exe",), phases=ffxiv),
        _sub(kind, "roblox", "Roblox", match="process", names=("roblox", "로블록스", "ロブロックス"), processes=("robloxplayerbeta.exe",), process_phase={"robloxplayerbeta.exe": "playing"}, phases=roblox),
        _sub(kind, "hunter", "怪物猎人", match="process", names=("怪物猎人", "monster hunter", "モンスターハンター", "몬스터헌터"), processes=("monsterhunterworld.exe", "monsterhunterwilds.exe"), phases=hunter),
        _sub(kind, "palworld", "幻兽帕鲁", match="process", names=("幻兽帕鲁", "palworld", "パルワールド", "팰월드"), processes=("palworld-win64-shipping.exe",), phases=palworld),
    )


def _listen(label: str) -> tuple[Phase, ...]:
    return (
        _phase("shelf", "在选歌", f"正在{label}里找歌", "还没在听。不要编歌名。", "他在找歌。不要替他点，不猜他想听什么心情。"),
        _phase("playing", "在听", "正在听歌。歌名：{title}。歌手：{artist}。歌词：{line}", "歌名、歌手或歌词空着就不要编。", "在听的时候可以接看见的歌名和一句歌词。不从歌词推断他的心情，不报下一首。", ("title", "artist", "line"), frames=1),
        _phase("paused", "已暂停", "音乐已暂停", "没有播放证据，不假装正在听。", "暂停时先安静，他开口再接。", ("title", "artist"), ahead=("playing",)),
    )


def _music() -> Kind:
    template = _listen("播放器")
    kind = Kind("music", "听听音乐", "music", False, 8, template, ())
    subs = (
        _sub(kind, "netease", "网易云音乐", match="split", names=("网易云", "网易云音乐"), processes=("cloudmusic.exe",), titles=("music.163.com", "y.music.163.com", "网易云音乐", "网易云"), process_phase={"cloudmusic.exe": "playing"}, phases=_listen("网易云音乐")),
        _sub(kind, "qqmusic", "QQ音乐", match="split", names=("qq音乐",), processes=("qqmusic.exe",), titles=("y.qq.com", "qq音乐"), process_phase={"qqmusic.exe": "playing"}, phases=_listen("QQ音乐")),
        _sub(kind, "kugou", "酷狗音乐", match="split", names=("酷狗", "酷狗音乐"), processes=("kugou.exe",), titles=("kugou.com", "酷狗音乐", "酷狗"), process_phase={"kugou.exe": "playing"}, phases=_listen("酷狗音乐")),
        _sub(kind, "kuwo", "酷我音乐", match="split", names=("酷我", "酷我音乐"), processes=("kwmusic.exe",), titles=("kuwo.cn", "酷我音乐"), process_phase={"kwmusic.exe": "playing"}, phases=_listen("酷我音乐")),
        _sub(kind, "spotify", "Spotify", match="split", names=("spotify", "スポティファイ"), processes=("spotify.exe",), titles=("open.spotify.com", "spotify"), process_phase={"spotify.exe": "playing"}, phases=_listen("Spotify")),
        _sub(kind, "youtubemusic", "YouTube Music", match="web", titles=("music.youtube.com", "youtube music"), phases=_listen("YouTube Music")),
        _sub(kind, "applemusic", "Apple Music", match="split", names=("apple music", "アップルミュージック", "애플뮤직"), processes=("applemusic.exe",), titles=("music.apple.com", "apple music"), process_phase={"applemusic.exe": "playing"}, phases=_listen("Apple Music")),
        _sub(kind, "amazonmusic", "Amazon Music", match="split", names=("amazon music",), processes=("amazon music.exe",), titles=("music.amazon.com", "music.amazon.co.jp", "amazon music"), process_phase={"amazon music.exe": "playing"}, phases=_listen("Amazon Music")),
        _sub(kind, "melon", "Melon", match="split", names=("melon", "멜론"), processes=("melon.exe",), titles=("melon.com", "멜론"), process_phase={"melon.exe": "playing"}, phases=_listen("Melon")),
        _sub(kind, "genie", "Genie", match="web", names=("지니", "genie music"), titles=("genie.co.kr", "지니뮤직"), phases=_listen("Genie")),
        _sub(kind, "flo", "FLO", match="web", names=("flo", "플로"), titles=("music-flo.com", "플로"), phases=_listen("FLO")),
        _sub(kind, "bugs", "Bugs", match="web", names=("bugs", "벅스"), titles=("music.bugs.co.kr", "벅스"), phases=_listen("Bugs")),
        _sub(kind, "vibe", "VIBE", match="web", names=("vibe", "바이브"), titles=("vibe.naver.com", "네이버 바이브", "naver vibe"), phases=_listen("VIBE")),
        _sub(kind, "linemusic", "LINE MUSIC", match="web", names=("line music", "ラインミュージック"), titles=("music.line.me", "line music", "linemusic"), phases=_listen("LINE MUSIC")),
        _sub(kind, "awa", "AWA", match="web", titles=("awa.fm", "awa music"), phases=_listen("AWA")),
        _sub(kind, "recochoku", "Recochoku", match="web", names=("レコチョク",), titles=("recochoku.jp", "レコチョク"), phases=_listen("Recochoku")),
    )
    return Kind(kind.id, kind.label, kind.scene, kind.configurable, kind.interval, kind.template, subs)


def _watch_film(label: str) -> tuple[Phase, ...]:
    return (
        _phase("picking", "在选片", f"正在{label}里选片。片名：{{title}}", "片名空着就不要编。", "他在挑片子。看清片名可以接一句想不想看，不剧透，不替他播。", ("title",), detail=True),
        _phase("playing", "在看", "正在看电影。片名：{title}。这一句：{line}", "片名或这一句空着就不要编情节。", "坐在旁边看。字幕看清了接这一句的反应，不剧透后面，不把片里的人说成他。", ("title", "line"), frames=3),
        _phase("paused", "已暂停", "影片已暂停", "没有新的情节，不补写。", "暂停时先安静，他问再讨论当前看到的部分。", ("title",), ahead=("playing",)),
        _phase("credits", "片尾", "片子放到片尾了。片名：{title}", "不要把全片情节复述一遍。", "片尾可以轻轻问看完的感觉。不总结主题，不剧透他没看到的部分。", ("title",)),
    )


def _movie() -> Kind:
    template = _watch_film("播放器")
    kind = Kind("movie", "看电影", "movie", False, 12, template, ())
    subs = (
        _sub(
            kind, "player", "本地播放器", match="process",
            processes=("potplayer.exe", "potplayermini64.exe", "potplayermini.exe", "vlc.exe", "mpc-hc64.exe", "mpv.exe", "qqplayer.exe", "gomplayer.exe"),
            process_phase={
                "potplayer.exe": "playing",
                "potplayermini64.exe": "playing",
                "potplayermini.exe": "playing",
                "vlc.exe": "playing",
                "mpc-hc64.exe": "playing",
                "mpv.exe": "playing",
                "qqplayer.exe": "playing",
                "gomplayer.exe": "playing",
            },
            phases=_watch_film("播放器"),
        ),
        _sub(kind, "iqiyi", "爱奇艺", match="split", names=("爱奇艺",), processes=("qyclient.exe", "qyplayer.exe"), titles=("iqiyi.com", "爱奇艺"), phases=_watch_film("爱奇艺")),
        _sub(kind, "qqlive", "腾讯视频", match="split", names=("腾讯视频",), processes=("qqlive.exe",), titles=("v.qq.com", "腾讯视频"), phases=_watch_film("腾讯视频")),
        _sub(kind, "youku", "优酷", match="split", names=("优酷",), processes=("youkudesktop.exe",), titles=("youku.com", "优酷"), phases=_watch_film("优酷")),
        _sub(kind, "netflix", "Netflix", match="split", names=("ネットフリックス", "넷플릭스"), processes=("netflix.exe",), titles=("netflix.com", "netflix"), phases=_watch_film("Netflix")),
        _sub(kind, "mgtv", "芒果TV", match="web", titles=("mgtv.com", "芒果tv", "芒果TV"), phases=_watch_film("芒果TV")),
        _sub(kind, "disney", "Disney+", match="web", names=("disney+", "ディズニープラス", "디즈니플러스"), titles=("disneyplus.com", "disney+"), phases=_watch_film("Disney+")),
        _sub(kind, "primevideo", "Prime Video", match="web", names=("prime video", "プライムビデオ"), titles=("primevideo.com", "amazon.com/gp/video", "amazon.co.jp/gp/video"), phases=_watch_film("Prime Video")),
        _sub(kind, "hulu", "Hulu", match="web", names=("フールー", "훌루"), titles=("hulu.com", "hulu.jp"), phases=_watch_film("Hulu")),
        _sub(kind, "max", "Max", match="web", titles=("play.max.com", "hbomax.com"), phases=_watch_film("Max")),
        _sub(kind, "unext", "U-NEXT", match="split", names=("ユーネクスト",), processes=("u-next.exe",), titles=("unext.jp", "u-next"), phases=_watch_film("U-NEXT")),
        _sub(kind, "tver", "TVer", match="web", names=("ティーバー",), titles=("tver.jp",), phases=_watch_film("TVer")),
        _sub(kind, "wavve", "Wavve", match="web", names=("웨이브",), titles=("wavve.com", "웨이브"), phases=_watch_film("Wavve")),
        _sub(kind, "tving", "TVING", match="web", names=("티빙",), titles=("tving.com", "티빙"), phases=_watch_film("TVING")),
        _sub(kind, "coupangplay", "Coupang Play", match="web", names=("쿠팡플레이",), titles=("coupangplay.com", "쿠팡플레이"), phases=_watch_film("Coupang Play")),
        _sub(kind, "watcha", "Watcha", match="web", names=("왓챠",), titles=("watcha.com", "왓챠"), phases=_watch_film("Watcha")),
        _sub(kind, "crunchyroll", "Crunchyroll", match="web", titles=("crunchyroll.com", "crunchyroll"), phases=_watch_film("Crunchyroll")),
    )
    return Kind(kind.id, kind.label, kind.scene, kind.configurable, kind.interval, kind.template, subs)


def _feed(label: str, *, live: bool) -> tuple[Phase, ...]:
    phases = [
        _phase("feed", "在刷", f"正在刷{label}。这一条：{{caption}}", "这一条空着就不要编内容。", f"在{label}里一条一条刷。这条看清了再接，没看清就安静，不催他停下。", ("caption",)),
        _phase("playing", "在看", f"正在看{label}。标题：{{title}}。这一句：{{caption}}", "标题或这一句空着就不要编。", "正片时接看见的标题和一句字幕。不把画面里的人说成他，不剧透。", ("title", "caption"), frames=3),
    ]
    if live:
        phases.append(_phase("live", "直播", f"正在看{label}的直播。主播：{{host}}。这一句：{{caption}}", "主播或这一句空着就不要编。", "直播里只接看见的主播和刚听到或刚看见的一句。不替他发弹幕，不编礼物。", ("host", "caption")))
    return tuple(phases)


def _video() -> Kind:
    template = _feed("视频", live=False)
    kind = Kind("video", "刷视频", "video", True, 5, template, ())
    subs = (
        _sub(kind, "bilibili", "哔哩哔哩", match="split", names=("哔哩哔哩", "b站"), processes=("哔哩哔哩.exe", "bilibiliuwpapp.exe"), titles=("bilibili.com", "哔哩哔哩", "b站"), phases=_feed("哔哩哔哩", live=True)),
        _sub(kind, "xiaohongshu", "小红书", match="web", titles=("xiaohongshu.com", "小红书"), phases=(
            _phase("feed", "在刷", "正在刷小红书。这一条：{caption}", "这一条空着就不要编。", "刷小红书时一条一条看。笔记看清了再接，不催他点赞。", ("caption",)),
            _phase("note", "图文", "正在看一篇小红书。标题：{title}", "标题空着就不要编笔记在说什么。", "图文看清标题再接一句。不把种草说成他已经买了。", ("title",), detail=True),
            _phase("playing", "在看", "正在看小红书视频。标题：{title}。这一句：{caption}", "标题或这一句空着就不要编。", "视频里接看见的一句。不剧透，不催评论。", ("title", "caption"), frames=3),
        )),
        _sub(kind, "douyin", "抖音", match="web", titles=("douyin.com", "抖音"), phases=_feed("抖音", live=True)),
        _sub(kind, "youtube", "YouTube", match="web", titles=("youtube.com", "youtu.be", "youtube"), phases=_feed("YouTube", live=True)),
        _sub(kind, "tiktok", "TikTok", match="web", titles=("tiktok.com", "tiktok"), phases=_feed("TikTok", live=True)),
        _sub(kind, "niconico", "niconico", match="web", names=("ニコニコ", "niconico"), titles=("nicovideo.jp", "niconico", "ニコニコ"), phases=_feed("niconico", live=True)),
        _sub(kind, "abema", "ABEMA", match="split", processes=("abematv.exe",), titles=("abema.tv", "abema"), phases=_feed("ABEMA", live=True)),
        _sub(kind, "twitch", "Twitch", match="split", processes=("twitch.exe",), titles=("twitch.tv", "twitch"), phases=_feed("Twitch", live=True)),
        _sub(kind, "soop", "SOOP", match="web", names=("숲", "afreecatv"), titles=("sooplive.co.kr", "play.sooplive.co.kr", "afreecatv.com"), phases=_feed("SOOP", live=True)),
        _sub(kind, "chzzk", "CHZZK", match="web", names=("치지직",), titles=("chzzk.naver.com", "치지직"), phases=_feed("CHZZK", live=True)),
        _sub(kind, "instagram", "Instagram", match="web", titles=("instagram.com", "instagram"), phases=_feed("Instagram", live=False)),
    )
    return Kind(kind.id, kind.label, kind.scene, kind.configurable, kind.interval, kind.template, subs)


def _work() -> Kind:
    template = (
        _phase("editing", "在做", "正在做这份工作。文件：{file}", "文件空着就不要编内容。", "他在做事。文件看清了可以轻轻提一句，看不清就别打断。", ("file",), detail=True),
    )
    kind = Kind("work", "工作", "code", True, 18, template, ())
    subs = (
        _sub(kind, "code", "写代码", match="process", scene="code", processes=("cursor.exe", "code.exe", "devenv.exe", "pycharm64.exe", "idea64.exe", "rider64.exe"), phases=(
            _phase("editing", "在写", "正在写代码。文件：{file}", "文件空着就不要编代码在做什么。", "写代码时尽量安静。文件名看清了可以提，不假装看懂实现。", ("file",), detail=True),
            _phase("running", "在跑", "代码正在跑。局面：{state}", "结果空着就不要说通过了或失败了。", "在跑的时候等结果。没看见输出就别下结论。", ("state",)),
            _phase("stuck", "卡住", "代码这里卡住了。报错：{error}", "报错空着就不要编原因。", "只把看见的报错原文交给他。不编修法，不装作已经看懂。", ("error",), detail=True),
        )),
        _sub(kind, "slides", "演示文稿", match="process", scene="slides", processes=("powerpnt.exe", "wpp.exe"), phases=(
            _phase("editing", "在改", "正在改这份演示。这一页：{page}", "这一页空着就不要编观点。", "改稿时看这一页想说什么。不盯着每一次改字。", ("page",), detail=True),
            _phase("showing", "放映", "正在放映。这一页：{page}", "这一页空着就不要编在讲什么。", "放映中少说话。这一页的观点看清了再接一句。", ("page",)),
        )),
        _sub(kind, "doc", "文档", match="process", scene="document", processes=("winword.exe", "excel.exe", "wps.exe", "et.exe"), phases=(
            _phase("editing", "在改", "正在改文档。文件：{file}", "文件空着就不要编正文。", "改文档时少打断。标题看清了可以接，不替他写。", ("file",), detail=True),
            _phase("reading", "在看", "正在看文档。文件：{file}", "看不清就不要复述正文。", "他在读。没有看清的句子就安静陪着。", ("file",)),
        )),
        _sub(kind, "hangul", "한글", match="process", scene="document", names=("한글", "한컴한글", "hwp"), processes=("hwp.exe",), phases=(
            _phase("editing", "在改", "正在改한글文档。文件：{file}", "文件空着就不要编正文。", "他在写韩文文档。标题看清了可以接，不替他写。", ("file",), detail=True),
            _phase("reading", "在看", "正在看한글文档。文件：{file}", "看不清就不要复述正文。", "他在读。没有看清的句子就安静陪着。", ("file",)),
        )),
        _sub(kind, "hshow", "한쇼", match="process", scene="slides", names=("한쇼", "hanshow"), processes=("hshow.exe",), phases=(
            _phase("editing", "在改", "正在改한쇼。这一页：{page}", "这一页空着就不要编观点。", "改韩文演示时看这一页。不盯着每一次改字。", ("page",), detail=True),
            _phase("showing", "放映", "正在放映한쇼。这一页：{page}", "这一页空着就不要编在讲什么。", "放映中少说话。这一页看清了再接一句。", ("page",)),
        )),
        _sub(kind, "gdocs", "Google Docs", match="web", scene="document", names=("google docs", "google ドキュメント", "google 문서", "google スプレッドシート", "google sheets", "google 스프레드시트"), titles=("docs.google.com/document", "docs.google.com/spreadsheets", "google docs", "google ドキュメント", "google 문서", "google sheets", "google スプレッドシート", "google 스프레드시트"), phases=(
            _phase("editing", "在改", "正在改 Google 文档。文件：{file}", "文件空着就不要编正文。", "网页文档里少打断。标题看清了可以接，不替他写。", ("file",), detail=True),
            _phase("reading", "在看", "正在看 Google 文档。文件：{file}", "看不清就不要复述正文。", "他在读。没有看清的句子就安静陪着。", ("file",)),
        )),
        _sub(kind, "gslides", "Google Slides", match="web", scene="slides", names=("google slides", "google スライド", "google 프레젠테이션"), titles=("docs.google.com/presentation", "google slides", "google スライド", "google 프레젠테이션"), phases=(
            _phase("editing", "在改", "正在改 Google 演示。这一页：{page}", "这一页空着就不要编观点。", "网页演示里看这一页想说什么。不盯着每一次改字。", ("page",), detail=True),
            _phase("showing", "放映", "正在放映 Google 演示。这一页：{page}", "这一页空着就不要编在讲什么。", "放映中少说话。这一页的观点看清了再接一句。", ("page",)),
        )),
        _sub(kind, "notion", "Notion", match="split", scene="document", processes=("notion.exe",), titles=("notion.so", "notion"), phases=(
            _phase("editing", "在改", "正在改 Notion。文件：{file}", "文件空着就不要编正文。", "他在记笔记。标题看清了可以接，不替他写。", ("file",), detail=True),
            _phase("reading", "在看", "正在看 Notion。文件：{file}", "看不清就不要复述正文。", "他在读一页。没有看清的句子就安静陪着。", ("file",)),
        )),
    )
    return Kind(kind.id, kind.label, kind.scene, kind.configurable, kind.interval, kind.template, subs)

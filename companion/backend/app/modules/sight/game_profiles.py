"""Per-title companion guidance, separate from visual detection."""
from __future__ import annotations

TITLE_PROFILES = {
    "英雄联盟": ("启动→大厅→排队→选英雄→加载→对线→团战→结算", "玩家英雄、分路、兵线、目标和死亡", "像开黑搭子，战斗时短句"),
    "地下城与勇士": ("登录→选角色→城镇→选副本→清图→首领→掉落", "角色、地图、副本、首领和掉落", "陪刷图，不教连招"),
    "穿越火线": ("大厅→房间→准备→回合→击杀→结算", "模式、阵营、回合、存活和目标", "回合间聊天，交火时安静"),
    "反恐精英2": ("大厅→购买→回合→下包→残局→结算", "回合、经济、包点、存活和胜负", "只讨论已发生的回合"),
    "刀塔2": ("大厅→选英雄→加载→对线→团战→Roshan→结算", "玩家英雄、线路、技能、塔和关键目标", "短句开黑，不指挥操作"),
    "艾尔登法环": ("菜单→探索→遭遇→首领→死亡→篝火", "区域、首领、死亡和探索进度", "陪探索，避免剧透"),
    "堡垒之夜": ("大厅→跳伞→搜集→交战→缩圈→决赛→结算", "落点、物资、圈、敌人和排名", "紧张节点短句"),
    "绝地求生": ("大厅→跳伞→搜集→跑圈→交战→淘汰→结算", "落点、装备、毒圈、击杀和排名", "像队友一样报关键变化"),
    "Apex英雄": ("大厅→跳伞→搜集→交战→倒地→复活→结算", "传奇、队伍、圈、击倒和复活", "团战短句，不喊技能"),
    "彩虹六号": ("大厅→选干员→准备→攻防回合→拆包→结算", "干员、攻防方、目标点、存活和拆包", "回合制陪看"),
    "侠盗猎车手5": ("菜单→自由模式→任务→追逐→任务结算", "任务目标、载具、追逐和任务结果", "开放世界少打断"),
    "荒野大镖客2": ("菜单→探索→任务→交火→营地→结算", "地点、任务、NPC和探索进度", "陪探索，避免剧透"),
    "怪物猎人世界": ("集会所→接任务→探索→狩猎→回营→结算", "猎人、怪物、部位、任务和素材", "只接看见的狩猎变化"),
    "怪物猎人：荒野": ("营地→任务→追踪→狩猎→采集→结算", "怪物状态、环境、任务和素材", "战斗时短句"),
    "赛博朋克2077": ("菜单→开放世界→任务→对话→战斗→任务结果", "当前任务、区域、选择和战斗", "剧情不抢话，不剧透"),
    "博德之门3": ("营地→探索→对话→检定→战斗→长休", "队伍、任务、检定、战斗和选择", "讨论选择，不替玩家决定"),
    "星露谷物语": ("农场→日程→耕作→采集→社交→睡觉", "日期、体力、作物、NPC和目标", "轻松陪伴，不催效率"),
    "幻兽帕鲁": ("基地→采集→制作→探索→捕捉→战斗", "基地、伙伴、资源、区域和首领", "只谈当前目标"),
    "文明7": ("开局→城市→科技→外交→战争→胜利", "回合、城市、科技、外交和胜利进度", "回合节点再说"),
}

# The remaining catalog entries are also explicit profiles, not genre fallbacks.
TITLE_PROFILES.update({
    "terraria": ("世界生成→采集→建造→探索→事件→Boss", "生命、装备、素材、NPC和Boss事件", "陪挖掘和建造，不催进度"),
    "minecraft": ("出生点→采集→建造→下界→末地→目标完成", "饥饿、资源、基地、维度和危险", "像一起生存的伙伴"),
    "rust": ("出生→采集→建家→制造→冲突→撤离", "基地、资源、装备、邻居和生存风险", "危险出现时短句提醒"),
    "dayz": ("出生→搜刮→补给→感染区→遭遇→撤离", "健康、食物、装备、地图和玩家遭遇", "紧张但不替他决策"),
    "left 4 dead 2": ("安全屋→路段→尸潮→特殊感染者→救援→结算", "队伍血量、特殊感染者、补给和安全屋", "尸潮时安静，安全屋再聊天"),
    "payday 2": ("选任务→潜入→警报→目标→撤离→分钱", "潜入状态、警报、目标、队友和撤离", "不提前剧透警报结果"),
    "dead by daylight": ("准备→修机→追逐→倒地→救援→逃生", "发电机、杀手、队友状态、钩子和出口", "追逐时不打断，转场再接话"),
    "hogwarts legacy": ("城堡→课程→探索→任务→战斗→奖励", "任务目标、区域、谜题和魔法战斗", "陪探索，不剧透剧情"),
    "the finals": ("大厅→选装备→回合→争夺现金箱→复活→决赛", "现金箱、队伍、复活、回合和淘汰", "只接回合转折，不喊操作"),
    "helldivers 2": ("舰桥→选星球→投放→任务目标→撤离→结算", "任务目标、增援、友伤、样本和撤离", "混乱时短句庆祝，不指挥"),
    "path of exile": ("城镇→地图→清图→稀有怪→Boss→掉落", "地图词缀、技能、生命、装备和掉落", "讨论构筑，不替玩家改Build"),
    "path of exile 2": ("城镇→探索→事件→Boss→装备→回城", "技能、资源、Boss机制、装备和地图", "新机制出现时再讨论"),
    "warframe": ("星图→选战甲→任务→目标→撤离→Mod", "战甲、任务目标、敌人、撤离和Mod", "陪刷任务，不报未确认掉落"),
    "destiny 2": ("轨道→活动→目标→遭遇→Boss→奖励", "火力队、机制、复活、Boss和掉落", "机制阶段短句"),
    "deadlock": ("大厅→选英雄→对线→推线→团战→核心", "英雄、线路、灵魂、守护者和核心", "像队友复盘但不指挥"),
    "team fortress 2": ("服务器→选兵种→推进→目标点→复活→胜负", "兵种、目标点、队伍和推进状态", "战斗短句，回合外聊天"),
    "garry's mod": ("服务器→沙盒→建造→事件→探索→离开", "当前模式、实体、玩家互动和目标", "以玩家当前玩法为中心"),
    "civilization vi": ("开局→城市→科技→外交→战争→胜利", "回合、城市、科技、资源、外交和胜利", "每回合只接重大决策"),
    "total war: three kingdoms": ("势力→内政→外交→行军→战斗→结算", "派系、粮食、军队、将领和战役目标", "战斗和内政分开聊"),
    "age of empires iv": ("时代→采集→建造→升级→交战→胜利", "资源、时代、城镇中心、军队和推进", "只报已发生的经济或战斗变化"),
    "rimworld": ("降落→建营地→生存→事件→危机→撤离", "殖民者心情、食物、医疗、建筑和袭击", "把殖民者当故事人物陪看"),
    "factorio": ("采矿→自动化→电力→科技→防御→火箭", "产线瓶颈、电力、污染、虫群和科技", "讨论系统变化，不替他改布局"),
    "hades": ("镜屋→武器→房间→祝福→Boss→死亡/逃脱", "武器、祝福、血量、房间和Boss", "失败也接住，不剧透"),
    "hades ii": ("营地→武器→区域→祝福→守关者→回营", "法阵、资源、祝福、守关者和成长", "鼓励尝试，不替玩家选流派"),
    "among us": ("房间→任务→紧急会议→投票→淘汰→胜负", "任务、尸体、会议、投票和阵营", "会议时不替玩家下结论"),
    "lethal company": ("公司→月球→搜刮→危险→撤离→配额", "配额、废料、队友、怪物和撤离", "危险时提醒一次，别刷屏"),
    "phasmophobia": ("准备→入屋→找证据→猎杀→撤离→奖励", "理智、证据、鬼房、猎杀和撤离", "恐怖节点短句，避免剧透"),
    "subnautica": ("逃生舱→采集→建造→深潜→蓝图→逃离", "氧气、深度、资源、基地和生物危险", "低氧和深潜时优先提醒"),
    "the elder scrolls online": ("城镇→任务→探索→副本→Boss→战利品", "任务线、区域、队伍、Boss和装备", "尊重剧情，不抢对白"),
    "starfield": ("飞船→星系→扫描→任务→交战→跃迁", "任务、飞船、燃料、星球和选择", "探索时少插话"),
    "fallout 4": ("避难所→聚落→探索→任务→战斗→建造", "聚落、任务、辐射、资源和派系", "不替玩家选派系"),
    "assassin's creed shadows": ("据点→侦察→潜入→战斗→任务→升级", "目标、警戒、角色切换、潜入和任务", "潜入时不打断"),
    "assassin's creed valhalla": ("聚落→航行→掠夺→任务→战斗→建设", "聚落、船队、任务、掠夺和选择", "历史探索陪伴，避免剧透"),
    "rocket league": ("大厅→选车→开球→攻防→加时→结算", "比分、球权、回合、队友和加时", "进球和关键防守才说"),
    "fall guys": ("匹配→赛道→障碍→晋级→决赛→夺冠", "当前赛道、淘汰线、晋级和决赛", "失败轻松接话，不复述每一步"),
    "dead island 2": ("安全屋→任务→探索→感染者→Boss→奖励", "任务、武器耐久、感染者和安全屋", "战斗简短，探索多陪伴"),
    "borderlands 3": ("避难所→任务→星球→战斗→Boss→掉落", "任务、Vault Hunter、武器词条、Boss和掉落", "只讨论看见的掉落"),
})

TITLE_PROFILES.update({
    'dark souls iii': ('传火祭祀场→区域探索→篝火→首领→死亡→回收灵魂', '血量、原素瓶、灵魂、捷径和首领血条', '死亡先接情绪；回收成功只庆祝一次；不剧透隐藏路线'),
    'sekiro': ('佛像→潜行→交锋→忍杀→首领→死亡/再战', '架势、忍杀点、葫芦、复生和当前敌人', '交锋时少说；失败后用户愿意才复盘，不责怪反应速度'),
    'the witcher 3': ('任务日志→探索→调查→对白选择→战斗→任务结果', '任务原文、猎魔委托、线索、角色对白和装备', '对白时静默；选择时讨论取舍；不泄露剧情和正确答案'),
})

# Keep the contract total: newly added launcher titles get their own named
# profile immediately, instead of silently falling into a genre profile.
from ..play.titles import TITLES  # noqa: E402
for _title in TITLES:
    _name = _title.names[0]
    _existing = next((TITLE_PROFILES[n] for n in _title.names if n in TITLE_PROFILES), None)
    if _existing:
        for _alias in _title.names:
            TITLE_PROFILES[_alias] = _existing
        continue
    TITLE_PROFILES.setdefault(_name, (
        "启动→大厅→游戏中→结算",
        f"{_name}当前画面的角色、目标、资源和明确结果",
        "只接新变化，不代操作，不猜测",
    ))


def profile_for(title: str) -> dict[str, str]:
    key = (title or "").strip()
    row = TITLE_PROFILES.get(key)
    if row is None:
        from ..play.titles import title_of
        matched = title_of(key)
        row = TITLE_PROFILES.get(matched.names[0]) if matched else None
    phases, focus, tone = row or ("菜单→游戏中→结算", f"{key or '当前游戏'}的角色、目标、资源和明确结果", "短句陪伴，不代操作，不猜测")
    return {"phases": phases, "focus": focus, "tone": tone}


def additional_subs(kind, existing):
    """Register named profiles in the actual detector and phase state machine."""
    from .model import Sub, Phase
    from ..play.titles import norm
    known = {norm(n) for sub in existing for n in (sub.label, *sub.names)}
    for index, title in enumerate(TITLES):
        if any(norm(n) in known for n in title.names):
            continue
        profile = profile_for(title.names[0])
        labels = profile['phases'].split('→')
        ids = tuple(f'stage_{i}' for i in range(len(labels)))
        phases = tuple(Phase(
            id=ids[i], label=label, slots=('state',), frames=2,
            say=f'{title.names[0]}：{label}。局面：{{state}}',
            speak='阶段需要当前画面文字或明确动作支持。未确认的角色、结果和资源留空。',
            company=f"{profile['tone']}。关注：{profile['focus']}。用户提问时围绕实际进度讨论；无新事实不重复评论。",
            ahead=tuple(pid for pid in ids if pid != ids[i]),
            mark=f'{title.names[0]}明确显示{label}的界面文字或动作，不以历史推断当前阶段',
        ) for i, label in enumerate(labels))
        yield Sub(id=f'catalog_{index}', label=title.names[0], kind=kind.id,
                  scene='game', match='process', names=title.names,
                  processes=tuple(p.lower() for p in title.processes
                                  if p.lower() not in {'launcher.exe', 'hl2.exe'}),
                  phases=phases)

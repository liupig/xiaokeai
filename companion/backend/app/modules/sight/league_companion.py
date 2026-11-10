"""Evidence-based event response choices, not a rotating canned phrase bank."""


def strategy(state: dict, events: list[str]) -> str:
    lines = [
        '【本轮LoL互动策略】一次只选一个交流点，台词自然生成，不照念策略、不固定句式。'
        '确认用户击杀就积极庆祝和认可，确认用户死亡就体贴地安慰、宽慰。方向明确，表达灵活；不要把沉默作为避免重复的主要办法。'
        '结合最近实际播出的台词，换措辞、句式和关注角度：不能只把帅换成厉害。保持角色性格稳定，不随机切换人设。'
        '顺风不浪、逆风不投是交流基调，不是每轮口号；不强迫继续玩，也不把击杀领先说成稳赢。',
    ]
    death = any('你被' in event and '击杀' in event for event in events)
    kill = any(event.startswith('你击杀了') for event in events)
    assist = any('参与助攻' in event for event in events)
    if death:
        # Count consecutive player deaths since their last kill in recorded API events.
        own = state.get('player_key')
        streak = 0
        for event in reversed(state.get('events') or []):
            if event.get('EventName') != 'ChampionKill':
                continue
            if event.get('KillerName') == own:
                break
            if own and event.get('VictimName') == own:
                streak += 1
        lines.append('本轮死亡：主动给一句有温度的宽慰。可接遗憾、给底气、陪他吐槽这一下、减轻一次失误的压力，选择贴合原话和关系的角度自然表达。不要抢着分析原因；不编交换收益或精彩操作。')
        if streak >= 2:
            lines.append('近期连续阵亡：回应更体贴，换一个宽慰角度，接住用户的具体吐槽；避免反复没事、加油和下波打回来，不训话、不比较水平。用户求分析才讨论一个有依据的点。')
        else:
            lines.append('把这次失误和玩家整体能力分开，让他感到你站在他这边；不用每次要求下把、换英雄或喝水。')
    elif kill:
        lines.append('本轮击杀：积极给情绪价值。可一起兴奋、替他得意、认可贡献、接起练习目标、俏皮庆祝或表达亲近的欣赏，选择最近没用过且符合关系的角度。避免连续同种开头、反问和称呼。只能围绕确认事实夸，不编操作细节。')
        if (state.get('scores') or {}).get('deaths', 0) >= 3:
            lines.append('已有多次阵亡：这次可作为一个积极变化，但不能断言翻盘、复仇或用户终于开心。')
    elif assist:
        lines.append('本轮助攻：积极认可参与和团队贡献，表达同样丰富，不把价值只等同人头；不知道过程就不编控制、保护或开团。')
    else:
        lines.append('闲时语料只作备选：基于本局确认的英雄，聊审美、机制趣味、英雄关系或玩家喜好。'
                     '先确认安全空档；纯API无法确认交战空档，因此不按定时器主动插入梗。'
                     '用户未接话不追问、不连续演角色。台词只用核实过的短句，不把自创句子冒充官方。')
        names = ' '.join(str(p.get('hero') or '') for p in state.get('roster', []))
        if '提莫' in names or 'Teemo' in names:
            lines.append('本局有提莫：安全闲聊时可偶尔接“团战可以输，提莫必须死”的玩家梗；明确只是玩笑，不当战术建议，不在用户阵亡或烦躁时使用。')
        if any(name in names for name in ('凯特琳', '女警', 'Caitlyn')):
            lines.append('本局有女警：闲聊可聊皮城警长、侦探与办案的轻松意象；不编爆头次数、射程优势已兑现或陷阱命中。')
    return '\n'.join(lines)

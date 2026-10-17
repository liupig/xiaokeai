"""在线流式 TTS：百炼 CosyVoice-v3-Flash（WebSocket 回调吐 PCM）。"""
from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Dict, List

COSY_VOICES = [
    {"id": "longanyang", "label": "龙安洋（阳光大男孩）", "lang": "zh-CN"},
    {"id": "longanhuan_v3", "label": "龙安欢（V3）（欢脱元气女）", "lang": "zh-CN"},
    {"id": "longanhuan", "label": "龙安欢（欢脱元气女）", "lang": "zh-CN"},
    {"id": "longhuhu_v3", "label": "龙呼呼（天真烂漫女童）", "lang": "zh-CN"},
    {"id": "longpaopao_v3", "label": "龙泡泡（飞天泡泡音）", "lang": "zh-CN"},
    {"id": "longjielidou_v3", "label": "龙杰力豆（阳光顽皮男）", "lang": "zh-CN"},
    {"id": "longxian_v3", "label": "龙仙（豪放可爱女）", "lang": "zh-CN"},
    {"id": "longling_v3", "label": "龙铃（稚气呆板女）", "lang": "zh-CN"},
    {"id": "longshanshan_v3", "label": "龙闪闪（戏剧化童声）", "lang": "zh-CN"},
    {"id": "longniuniu_v3", "label": "龙牛牛（阳光男童声）", "lang": "zh-CN"},
    {"id": "longjiaxin_v3", "label": "龙嘉欣（优雅粤语女）", "lang": "zh-CN"},
    {"id": "longjiayi_v3", "label": "龙嘉怡（知性粤语女）", "lang": "zh-CN"},
    {"id": "longanyue_v3", "label": "龙安粤（欢脱粤语男）", "lang": "zh-CN"},
    {"id": "longlaotie_v3", "label": "龙老铁（东北直率男）", "lang": "zh-CN"},
    {"id": "longshange_v3", "label": "龙陕哥（原味陕北男）", "lang": "zh-CN"},
    {"id": "longanmin_v3", "label": "龙安闽（清纯萝莉女）", "lang": "zh-CN"},
    {"id": "loongkyong_v3", "label": "loongkyong（韩语女）", "lang": "ko"},
    {"id": "loongriko_v3", "label": "Riko（二次元霓虹女）", "lang": "ja"},
    {"id": "loongtomoka_v3", "label": "loongtomoka（日语女）", "lang": "ja"},
    {"id": "loongabby_v3", "label": "loongabby（美式英文女）", "lang": "en"},
    {"id": "loongandy_v3", "label": "loongandy（美式英文男）", "lang": "en"},
    {"id": "loongannie_v3", "label": "loongannie（美式英文女）", "lang": "en"},
    {"id": "loongava_v3", "label": "loongava（美式英文女）", "lang": "en"},
    {"id": "loongbeth_v3", "label": "loongbeth（美式英文女）", "lang": "en"},
    {"id": "loongbetty_v3", "label": "loongbetty（美式英文女）", "lang": "en"},
    {"id": "loongcally_v3", "label": "loongcally（美式英文女）", "lang": "en"},
    {"id": "loongcindy_v3", "label": "loongcindy（美式英文女）", "lang": "en"},
    {"id": "loongdavid_v3", "label": "loongdavid（美式英文男）", "lang": "en"},
    {"id": "loongdonna_v3", "label": "loongdonna（美式英文女）", "lang": "en"},
    {"id": "loongemily_v3", "label": "loongemily（英式英文女）", "lang": "en"},
    {"id": "loongeric_v3", "label": "loongeric（英式英文男）", "lang": "en"},
    {"id": "loongluna_v3", "label": "loongluna（英式英文女）", "lang": "en"},
    {"id": "loongluca_v3", "label": "loongluca（英式英文男）", "lang": "en"},
    {"id": "loongtomoya_v3", "label": "loongtomoya（日语男）", "lang": "ja"},
    {"id": "loongyuuna_v3", "label": "Yuuna（日语女）", "lang": "ja"},
    {"id": "loongyuuma_v3", "label": "Yuuma（日语男）", "lang": "ja"},
    {"id": "loongjihun_v3", "label": "Jihun（韩语男）", "lang": "ko"},
    {"id": "loongindah_v3", "label": "loongindah（印尼女）", "lang": "zh-CN"},
    {"id": "longfei_v3", "label": "龙飞（热血磁性男）", "lang": "zh-CN"},
    {"id": "longyingxiao_v3", "label": "龙应笑（清甜推销女）", "lang": "zh-CN"},
    {"id": "longyingxun_v3", "label": "龙应询（年轻青涩男）", "lang": "zh-CN"},
    {"id": "longyingjing_v3", "label": "龙应静（低调冷静女）", "lang": "zh-CN"},
    {"id": "longyingling_v3", "label": "龙应聆（温和共情女）", "lang": "zh-CN"},
    {"id": "longyingtao_v3", "label": "龙应桃（温柔淡定女）", "lang": "zh-CN"},
    {"id": "longxiaochun_v3", "label": "龙小淳（知性积极女）", "lang": "zh-CN"},
    {"id": "longxiaoxia_v3", "label": "龙小夏（沉稳权威女）", "lang": "zh-CN"},
    {"id": "longyumi_v3", "label": "YUMI（正经青年女）", "lang": "zh-CN"},
    {"id": "longanyun_v3", "label": "龙安昀（居家暖男）", "lang": "zh-CN"},
    {"id": "longanwen_v3", "label": "龙安温（优雅知性女）", "lang": "zh-CN"},
    {"id": "longanli_v3", "label": "龙安莉（利落从容女）", "lang": "zh-CN"},
    {"id": "longanlang_v3", "label": "龙安朗（清爽利落男）", "lang": "zh-CN"},
    {"id": "longyingmu_v3", "label": "龙应沐（优雅知性女）", "lang": "zh-CN"},
    {"id": "longantai_v3", "label": "龙安台（嗲甜台湾女）", "lang": "zh-CN"},
    {"id": "longhua_v3", "label": "龙华（元气甜美女）", "lang": "zh-CN"},
    {"id": "longcheng_v3", "label": "龙橙（智慧青年男）", "lang": "zh-CN"},
    {"id": "longze_v3", "label": "龙泽（温暖元气男）", "lang": "zh-CN"},
    {"id": "longzhe_v3", "label": "龙哲（呆板大暖男）", "lang": "zh-CN"},
    {"id": "longyan_v3", "label": "龙颜（温暖春风女）", "lang": "zh-CN"},
    {"id": "longxing_v3", "label": "龙星（温婉邻家女）", "lang": "zh-CN"},
    {"id": "longtian_v3", "label": "龙天（磁性理智男）", "lang": "zh-CN"},
    {"id": "longwan_v3", "label": "龙婉（细腻柔声女）", "lang": "zh-CN"},
    {"id": "longqiang_v3", "label": "龙嫱（浪漫风情女）", "lang": "zh-CN"},
    {"id": "longfeifei_v3", "label": "龙菲菲（甜美娇气女）", "lang": "zh-CN"},
    {"id": "longhao_v3", "label": "龙浩（多情忧郁男）", "lang": "zh-CN"},
    {"id": "longanrou_v3", "label": "龙安柔（温柔闺蜜女）", "lang": "zh-CN"},
    {"id": "longhan_v3", "label": "龙寒（温暖痴情男）", "lang": "zh-CN"},
    {"id": "longanzhi_v3", "label": "龙安智（睿智轻熟男）", "lang": "zh-CN"},
    {"id": "longanling_v3", "label": "龙安灵（思维灵动女）", "lang": "zh-CN"},
    {"id": "longanya_v3", "label": "龙安雅（高雅气质女）", "lang": "zh-CN"},
    {"id": "longanqin_v3", "label": "龙安亲（亲和活泼女）", "lang": "zh-CN"},
    {"id": "longmiao_v3", "label": "龙妙（抑扬顿挫女）", "lang": "zh-CN"},
    {"id": "longsanshu_v3", "label": "龙三叔（沉稳质感男）", "lang": "zh-CN"},
    {"id": "longyuan_v3", "label": "龙媛（温暖治愈女）", "lang": "zh-CN"},
    {"id": "longyue_v3", "label": "龙悦（温暖磁性女）", "lang": "zh-CN"},
    {"id": "longxiu_v3", "label": "龙修（博才说书男）", "lang": "zh-CN"},
    {"id": "longnan_v3", "label": "龙楠（睿智青年男）", "lang": "zh-CN"},
    {"id": "longwanjun_v3", "label": "龙婉君（细腻柔声女）", "lang": "zh-CN"},
    {"id": "longyichen_v3", "label": "龙逸尘（洒脱活力男）", "lang": "zh-CN"},
    {"id": "longlaobo_v3", "label": "龙老伯（沧桑岁月爷）", "lang": "zh-CN"},
    {"id": "longlaoyi_v3", "label": "龙老姨（烟火从容阿姨）", "lang": "zh-CN"},
    {"id": "longjiqi_v3", "label": "龙机器（呆萌机器人）", "lang": "zh-CN"},
    {"id": "longhouge_v3", "label": "龙猴哥（经典猴哥）", "lang": "zh-CN"},
    {"id": "longdaiyu_v3", "label": "龙黛玉（娇率才女音）", "lang": "zh-CN"},
    {"id": "longanran_v3", "label": "龙安燃（活泼质感女）", "lang": "zh-CN"},
    {"id": "longanxuan_v3", "label": "龙安宣（经典直播女）", "lang": "zh-CN"},
    {"id": "longshuo_v3", "label": "龙硕（博才干练男）", "lang": "zh-CN"},
    {"id": "longshu_v3", "label": "龙书（沉稳青年男）", "lang": "zh-CN"},
    {"id": "loongbella_v3", "label": "Bella3.0（精准干练女）", "lang": "zh-CN"},
]
SAMPLE_RATE = 24000
MODEL = "cosyvoice-v3-flash"


def voice_ids() -> set:
    return {v["id"] for v in COSY_VOICES}


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "cosy"} for v in COSY_VOICES]


async def synthesize_pcm(text: str, voice: str, api_key: str) -> AsyncIterator[bytes]:
    """边合成边产出 24kHz / 16bit / mono PCM。"""
    if not api_key.strip():
        raise RuntimeError("未配置百炼 API Key，请在设置 → AI 对话里填写")
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不被 CosyVoice 支持")

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def put(item) -> None:
        loop.call_soon_threadsafe(q.put_nowait, item)

    def worker() -> None:
        try:
            import dashscope
            from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

            class CB(ResultCallback):
                def on_data(self, data: bytes) -> None:
                    if data:
                        put(("data", data))

                def on_complete(self) -> None:
                    put(("done", b""))

                def on_error(self, message: str) -> None:
                    put(("error", str(message)))

            dashscope.api_key = api_key
            syn = SpeechSynthesizer(
                model=MODEL,
                voice=voice,
                format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                callback=CB(),
            )
            syn.call(text)
            put(("done", b""))
        except Exception as exc:
            put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True, name="cosy-tts").start()
    finished = False
    while not finished:
        kind, payload = await q.get()
        if kind == "data":
            yield payload
        elif kind == "error":
            raise RuntimeError(payload)
        else:
            finished = True

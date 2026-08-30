"""对话窗口：prompt 历史和记忆抽取共用同一套尺度。"""

# 一轮 = 用户一句 + 助手一句。prompt 里留这么多 QA。
HISTORY_TURNS = 10
HISTORY_QA_MESSAGES = HISTORY_TURNS * 2
HISTORY_FETCH = 80

# 还差一轮滑出窗口时抽一次；重叠两轮给 Mem0 上下文，其它历史不再送。
EXTRACT_NEW_TURNS = HISTORY_TURNS - 1
EXTRACT_OVERLAP_TURNS = 2

SIDE_KINDS = {"delayed", "proactive", "goodbye", "welcome", "aside"}

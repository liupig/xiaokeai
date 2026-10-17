"""对话窗口：prompt 历史和记忆抽取共用同一套尺度。"""

# 一轮 = 用户一句 + 助手一句。prompt 里留这么多 QA。
HISTORY_TURNS = 10
HISTORY_QA_MESSAGES = HISTORY_TURNS * 2
HISTORY_FETCH = 80

# 四轮就抽。十轮窗口里还留着后面的话，抽取慢一点，开头也不会先被挤掉。
EXTRACT_NEW_TURNS = 4
EXTRACT_OVERLAP_TURNS = 2

SIDE_KINDS = {"delayed", "proactive", "goodbye", "welcome", "aside"}

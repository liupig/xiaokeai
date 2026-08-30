"""本地 Mock OpenAI 兼容服务：用于无 API Key 时端到端验证聊天管线。

用法：python tests/mock_llm.py  （监听 127.0.0.1:8788）
把设置里 LLM base_url 填 http://127.0.0.1:8788/v1，api_key 随便填。
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

REPLY = (
    "[emo:happy]小哥哥你来啦～[act:wave]今天想聊点什么呀？"
    "[emo:relaxed]要不要我给你跳一支舞放松一下？"
)


@app.post("/v1/chat/completions")
async def completions():
    async def gen():
        # 按 3 字符一个 chunk 模拟真实流式（标签会被跨 chunk 切开，测试解析器）
        for i in range(0, len(REPLY), 3):
            chunk = {
                "choices": [{"delta": {"content": REPLY[i:i + 3]}}]
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8788, log_level="warning")

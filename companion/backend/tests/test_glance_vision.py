"""陪看视觉模型的调用方式和聊天模型一样，像素不留在结果里。"""
from app.modules.glance.vision import build_payload, parse_completion, uses_local


def test_local_minicpm_is_the_default_provider():
    assert uses_local({"provider": "minicpm"}) is True
    assert uses_local({"provider": "openai"}) is False
    assert uses_local({}) is True


def test_other_vision_models_get_images_like_an_llm():
    payload = build_payload(
        {"model": "qwen-vl-max"},
        "只写屏幕事实",
        ["aaa", "data:image/jpeg;base64,bbb"],
    )
    content = payload["messages"][0]["content"]
    assert payload["model"] == "qwen-vl-max"
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,aaa")
    assert content[2]["image_url"]["url"] == "data:image/jpeg;base64,bbb"


def test_completion_text_is_kept_and_pixels_are_not():
    text = parse_completion({"choices": [{"message": {"content": "界面：播放器\n类型：movie"}}]})
    assert "播放器" in text
    listed = parse_completion({
        "choices": [{"message": {"content": [{"type": "text", "text": "标题：夜曲"}]}}],
    })
    assert listed == "标题：夜曲"

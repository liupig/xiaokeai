from app.services.direct_commands import direct_outfit_event
from app.services.llm import TagStreamParser


def test_live2d_capability_tags_are_events_not_speech():
    parser = TagStreamParser()
    events = parser.feed(
        "你好[motion:Touch:1][outfit:round_glasses:on]"
        "[param:ParamAngleX=0.5][preset:cat_girl]明天见"
    )

    assert events == [
        {"type": "text", "delta": "你好"},
        {"type": "motion", "value": "Touch:1"},
        {"type": "outfit", "value": "round_glasses:on"},
        {"type": "param", "value": "ParamAngleX=0.5"},
        {"type": "preset", "value": "cat_girl"},
        {"type": "text", "delta": "明天见"},
    ]
    assert parser.flush() == []


def test_invalid_live2d_values_are_safe_events():
    parser = TagStreamParser()
    events = parser.feed("[motion:][param:ParamAngleX=abc]")

    assert events[0] == {"type": "text", "delta": "[motion:]"}
    assert events[1] == {"type": "param", "value": "ParamAngleX=abc"}



def test_remove_glasses_command_is_deterministic():
    assert direct_outfit_event("把眼镜摘掉。") == {"type": "outfit", "value": "glasses:off"}
    assert direct_outfit_event("取下眼镜") == {"type": "outfit", "value": "glasses:off"}
    assert direct_outfit_event("不要带眼镜了") == {"type": "outfit", "value": "glasses:off"}
    assert direct_outfit_event("别带眼镜") == {"type": "outfit", "value": "glasses:off"}
    assert direct_outfit_event("摘掉圆眼镜") == {"type": "outfit", "value": "glasses:off"}
    assert direct_outfit_event("眼镜好看吗") is None


def test_wear_glasses_command_is_deterministic():
    assert direct_outfit_event("戴上圆眼镜") == {"type": "outfit", "value": "round_glasses:on"}
    assert direct_outfit_event("戴上方眼镜") == {"type": "outfit", "value": "square_glasses:on"}
    assert direct_outfit_event("戴上眼镜") == {"type": "outfit", "value": "glasses:on"}
    assert direct_outfit_event("眼镜好看吗") is None

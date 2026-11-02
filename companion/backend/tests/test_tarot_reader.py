"""Reading context must preserve player focus and hidden information."""
from app.modules.tarot import reader


def state(phase="linger", focus=None):
    return {"spread": "advice", "phase": phase, "question": "是否换工作",
            "focus": focus, "revealed": [0, 1], "cards": [
                {"id": "09-hermit", "name": "隐者", "position": "现状"},
                {"id": "16-tower", "name": "塔", "position": "阻碍"},
                {"id": "17-star", "name": "秘密牌名", "position": "建议"}]}


def test_unfocused_followup_does_not_force_last_card():
    task = reader.turn_task(state())
    assert "对方点哪张或问哪张" in task
    assert "对方在追问第2张" not in task
    assert "是否换工作" in task


def test_hidden_card_does_not_leak_into_reading_context():
    st = state("open", 0)
    assert "秘密牌名" not in reader.turn_task(st)
    assert "秘密牌名" not in reader.reading_cue(st, "这张呢")
    assert "这一轮就讲这张" in reader.turn_task(st)


def test_clarifier_identifies_original_card():
    st = state()
    st["cards"][1].update(clarifier=True, host=0)
    text = reader.card_lines(st["cards"], 1, st["revealed"])
    assert "补充第1张隐者" in text
    assert "解释原牌，不覆盖原牌" in text


def test_synthesis_waits_for_complete_spread_and_clears_focus(monkeypatch):
    from app.modules.tarot import service
    st = state("open", 0)
    monkeypatch.setattr(service, "_sessions", {98765: st})
    service.start_synth(98765)
    assert st["phase"] == "open"
    st["revealed"].append(2)
    service.start_synth(98765)
    assert st["phase"] == "synth"
    assert st["focus"] is None
    assert st["want_synth"] is True
    service.mark_synth_done(98765)
    assert st["phase"] == "linger"
    assert st["want_synth"] is False
    service.start_synth(98765)
    assert st["phase"] == "synth"


def test_last_reveal_waits_for_player_to_request_summary(monkeypatch):
    from app.modules.tarot import service
    st = state("open", 0)
    monkeypatch.setattr(service, "_sessions", {98765: st})
    service.reveal(98765, 2)
    assert st["phase"] == "open"
    assert st["want_synth"] is False


def test_synthesis_prompt_answers_question_before_explaining():
    st = state("synth")
    st["revealed"].append(2)
    task = reader.turn_task(st)
    assert "第一句直接回应原问题" in task
    assert "结论成立的条件" in task
    assert "补充或修正原结论" in task

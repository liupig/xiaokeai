"""魅影酒馆：牌组、揭穿、开枪、手牌不外泄。不连网络。"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.flags import MODULE_KEYS, _DEFAULT_OFF  # noqa: E402
from app.modules.tavern.judge import normalize, parse_decision  # noqa: E402
from app.modules.tavern.rules import (  # noqa: E402
    COUNTS,
    Gun,
    RuleError,
    Table,
    build_deck,
    face_of,
    honest,
)


def test_chat_phrase_opens_the_tavern():
    from app.modules.tavern.wake import invite_hint, wants_tavern

    assert wants_tavern("我们去魅影酒馆坐坐")
    assert wants_tavern("玩酒馆")
    assert wants_tavern("开一局酒馆")
    assert not wants_tavern("不去酒馆")
    assert not wants_tavern("看看今天的金价")
    assert not wants_tavern("来看牌")
    assert "入座" in invite_hint("去酒馆")
    assert invite_hint("今天天气不错") == ""


def test_tavern_is_a_module_and_defaults_on():
    assert "tavern" in MODULE_KEYS
    assert "tavern" not in _DEFAULT_OFF


def test_deck_is_twenty_with_two_wilds():
    deck = build_deck()
    assert len(deck) == 20
    assert len(set(deck)) == 20
    assert Counter(face_of(card) for card in deck) == Counter(COUNTS)
    assert honest("mei:1", "lady")
    assert honest("ying:2", "loli")
    assert honest("girl:3", "girl")
    assert not honest("girl:3", "loli")


def test_gun_fires_the_loaded_chamber():
    gun = Gun(1)
    assert gun.fire() is False
    assert gun.fire() is True
    assert gun.pulls == 2


def _ready(seed: int = 0) -> Table:
    table = Table(her_name="清宵", rng=random.Random(seed))
    table.start()
    for seat in table.seats:
        seat.alive = True
        seat.hand = ["loli:1"] if seat.id == "you" else [f"girl:{table.index(seat.id) + 2}"]
    table.table = "loli"
    table.pile = None
    table.phase = "act"
    table.show = None
    table.turn = table.index("you")
    return table


def test_a_true_play_shoots_the_caller():
    table = _ready()
    nxt = table.seats[(table.turn + 1) % 4]
    nxt.gun = Gun(5)
    table.play(["loli:1"])
    table.call()
    assert table.show["honest"] is True
    assert table.show["shooter"] == nxt.id
    assert table.show["hit"] is False
    assert nxt.alive is True
    assert nxt.gun.pulls == 1


def test_a_lie_shoots_the_actor_and_a_wild_is_not_a_lie():
    table = _ready()
    you = table.seat("you")
    you.hand = ["girl:9"]
    you.gun = Gun(0)
    table.play(["girl:9"])
    table.call()
    assert table.show["honest"] is False
    assert table.show["shooter"] == "you"
    assert table.show["hit"] is True
    assert you.alive is False

    table = _ready()
    table.seat("you").hand = ["mei:19"]
    table.table = "lady"
    table.play(["mei:19"])
    table.call()
    assert table.show["honest"] is True
    assert table.show["shooter"] != "you"


def test_opening_cannot_be_called_and_four_cards_are_refused():
    table = _ready()
    try:
        table.call()
        raised = False
    except RuleError as exc:
        raised = str(exc) == "nocall"
    assert raised
    table.seat("you").hand = ["loli:1", "loli:2", "loli:3", "loli:4"]
    try:
        table.play(["loli:1", "loli:2", "loli:3", "loli:4"])
        refused = False
    except RuleError as exc:
        refused = str(exc) == "count"
    assert refused


def test_a_failed_challenge_lets_the_caller_name_the_next_suit():
    table = _ready()
    you = table.seat("you")
    you.hand = ["loli:1"]
    nxt = table.seats[(table.turn + 1) % 4]
    nxt.gun = Gun(5)
    table.play(["loli:1"])
    table.call()
    assert table.show["honest"] is True
    assert table.show["shooter"] == nxt.id
    assert table.show["hit"] is False
    table.ack()
    assert table.phase == "name"
    assert table.table == ""
    assert table.seats[table.turn].id == nxt.id
    table.name("girl")
    assert table.phase == "act"
    assert table.table == "girl"
    assert table.pile is None
    played = table.seat(nxt.id).hand[:2]
    table.play(played)
    assert table.pile["actor"] == nxt.id
    assert len(table.pile["cards"]) == len(played)
    assert table.seats[table.turn].id != nxt.id


def test_a_true_challenge_lets_the_actor_name_if_they_live():
    table = _ready()
    you = table.seat("you")
    you.hand = ["girl:1", "girl:2", "lady:3"]
    you.gun = Gun(5)
    table.play(["girl:1", "girl:2"])
    table.call()
    assert table.show["honest"] is False
    assert table.show["shooter"] == "you"
    assert table.show["hit"] is False
    table.ack()
    assert table.phase == "name"
    assert table.seats[table.turn].id == "you"
    assert table.seat("you").hand == ["lady:3"]
    table.name("lady")
    assert table.table == "lady"
    one = table.seat("you").hand[:1]
    table.play(one)
    assert table.pile["actor"] == "you"
    assert len(table.pile["cards"]) == 1


def test_cards_come_back_only_when_the_table_is_empty():
    table = _ready()
    you = table.seat("you")
    you.hand = ["girl:1"]
    you.gun = Gun(5)
    table.play(["girl:1"])
    table.call()
    table.ack()
    assert you.hand == []
    assert table.phase == "name"
    table.name("lady")
    assert table.phase == "act"
    assert table.table == "lady"
    assert table.seats[table.turn].id != "you"
    assert table.seats[table.turn].hand

    for seat in table.seats:
        seat.hand = []
    table.phase = "show"
    table.show = {"kind": "clear", "who": "you"}
    table.ack()
    assert table.phase == "act"
    assert all(len(seat.hand) == 5 for seat in table.seats)


def test_a_death_does_not_deal_cards_back():
    table = _ready()
    you = table.seat("you")
    you.hand = []
    table.seat("qin").hand = ["girl:2", "girl:3"]
    table.seat("her").hand = ["lady:1"]
    table.seat("bar").alive = False
    table.seat("bar").hand = []
    table.phase = "show"
    table.show = {
        "kind": "reveal", "hit": True, "shooter": "bar",
        "actor": "bar", "caller": "qin", "honest": False, "cards": ["loli:2"],
    }
    table.ack()
    assert you.hand == []
    assert table.seat("qin").hand == ["girl:2", "girl:3"]
    assert table.seat("her").hand == ["lady:1"]
    assert table.phase == "act"

    for seat in table.seats:
        if seat.alive:
            seat.hand = []
    table.phase = "show"
    table.show = {
        "kind": "reveal", "hit": True, "shooter": "qin",
        "actor": "qin", "caller": "her", "honest": False, "cards": ["girl:2"],
    }
    table.seat("qin").alive = False
    table.ack()
    assert you.hand == []
    assert table.phase == "over"
    assert table.winner == "her"


def test_a_fatal_ritual_returns_the_suit_to_the_house():
    table = _ready()
    you = table.seat("you")
    you.hand = ["girl:1"]
    you.gun = Gun(0)
    table.play(["girl:1"])
    table.call()
    assert table.show["hit"] is True
    assert you.alive is False
    table.ack()
    assert table.phase == "act"
    assert table.table in ("loli", "girl", "lady")
    assert you.alive is False
    assert you.hand == []
    assert table.note["dealt"] is False
    assert "you" not in table.note["seated"]


def test_brief_shows_only_the_current_hand():
    table = _ready()
    table.turn = table.index("qin")
    table.seat("qin").hand = ["mei:1", "loli:2"]
    table.seat("you").hand = ["ying:1"]
    info = table.brief()
    raw = json.dumps(info)
    assert "ying:1" not in raw
    assert "mei:1" in raw
    assert "bullet" not in raw
    assert info["who"] == "qin"


def test_ai_follows_a_model_decision():
    table = _ready()
    table.turn = table.index("qin")
    table.seat("qin").hand = ["lady:1", "loli:2", "girl:3"]
    table.pile = {"actor": "you", "cards": ["girl:9"]}
    table.step({"act": "call"})
    assert table.phase == "show"
    assert table.show["caller"] == "qin"


def test_ai_plays_the_cards_the_model_picked():
    table = _ready()
    table.turn = table.index("bar")
    table.seat("bar").hand = ["lady:1", "lady:2", "girl:3"]
    table.pile = None
    table.step({"act": "play", "cards": ["lady:2", "girl:3"]})
    assert table.pile["cards"] == ["lady:2", "girl:3"]


def test_a_bad_model_decision_falls_back_to_a_legal_play():
    table = _ready()
    table.turn = table.index("her")
    table.seat("her").hand = ["loli:4"]
    table.pile = None
    table.step({"act": "play", "cards": ["mei:1"]})
    assert table.pile["actor"] == "her"
    assert table.pile["cards"] == ["loli:4"]


def test_model_names_the_suit_after_the_rite():
    table = _ready()
    table.phase = "name"
    table.table = ""
    table.turn = table.index("qin")
    table.seat("qin").hand = ["girl:1", "lady:2"]
    table.step({"face": "lady"})
    assert table.table == "lady"
    assert table.phase == "act"
    assert table.seats[table.turn].id == "qin"


def test_a_spoken_line_is_kept_and_a_missing_one_is_filled():
    table = _ready()
    table.turn = table.index("qin")
    table.seat("qin").hand = ["lady:1", "loli:2"]
    table.pile = {"actor": "you", "cards": ["girl:1"]}
    table.step({"act": "call", "line": "太顺了，我不信。"})
    assert table.note["line"] == "太顺了，我不信。"
    assert table.show["caller"] == "qin"

    table = _ready()
    table.turn = table.index("bar")
    table.table = "lady"
    table.seat("bar").hand = ["lady:1"]
    table.pile = None
    table.step({"act": "play", "cards": ["lady:1"]})
    assert table.note["line"] == "我先出。一张御姐。"
    assert table.note["follow"] is False

    brief = {"phase": "act", "pile": {"actor": "you", "n": 1}, "hand": ["loli:1", "girl:2"]}
    got = normalize(brief, '{"act":"call","line":"girl:1 太顺了，我不信。"}')
    assert got is not None
    assert got["act"] == "call"
    assert got["line"] == "太顺了，我不信。"


def test_parse_decision_reads_a_fenced_json():
    got = parse_decision('想了想\n```json\n{"act":"call"}\n```')
    assert got is not None and got["act"] == "call"
    brief = {"phase": "act", "pile": {"actor": "you", "n": 1}, "hand": ["loli:1", "girl:2"]}
    assert normalize(brief, '{"act":"play","cards":["少女"]}') == {"act": "play", "cards": ["girl:2"]}
    named = {"phase": "name", "hand": ["lady:1"]}
    assert normalize(named, '{"face":"御姐"}') == {"face": "lady"}


def test_view_hides_other_hands_and_the_bullet():
    table = _ready()
    table.seat("you").hand = ["loli:1"]
    table.seat("qin").hand = ["mei:19"]
    table.seat("qin").gun = Gun(3)
    raw = json.dumps(table.view(), ensure_ascii=False)
    assert "mei:19" not in raw
    assert "loli:1" in raw
    assert "bullet" not in raw


def test_the_last_two_open_a_new_round_without_the_people_who_already_finished():
    table = _ready()
    table.table = "loli"
    table.seat("you").hand = ["loli:1"]
    table.seat("bar").hand = ["loli:2"]
    table.seat("her").hand = ["girl:1", "girl:2"]
    table.seat("qin").hand = ["lady:1", "lady:2"]
    table.turn = table.index("you")
    table.play(["loli:1"])
    assert table.duel == []
    assert table.seats[table.turn].id == "bar"
    table.play(["loli:2"])
    assert set(table.duel) == {"her", "qin"}
    assert set(table.aside) == {"you", "bar"}
    table.seat("her").hand = []
    table.seat("qin").hand = []
    table.phase = "show"
    table.show = {"kind": "clear", "who": "qin"}
    table.ack()
    assert table.note["dealt"] is True
    assert set(table.note["seated"]) == {"her", "qin"}
    assert len(table.seat("her").hand) == 5
    assert len(table.seat("qin").hand) == 5
    assert table.seat("you").alive and table.seat("you").hand == []
    assert table.seat("bar").alive and table.seat("bar").hand == []


def test_one_empty_hand_after_the_rite_starts_a_fresh_two_player_round():
    table = _ready()
    table.duel = ["you", "qin"]
    table.aside = ["bar", "her"]
    table.seat("bar").hand = []
    table.seat("her").hand = []
    table.seat("you").hand = []
    table.seat("qin").hand = ["lady:1", "lady:2", "girl:1"]
    table.phase = "show"
    table.show = {
        "kind": "reveal", "hit": False, "shooter": "you",
        "actor": "you", "caller": "qin", "honest": False, "cards": ["loli:1"],
    }
    table.ack()
    assert table.note["dealt"] is True
    assert set(table.note["seated"]) == {"you", "qin"}
    assert len(table.seat("you").hand) == 5
    assert len(table.seat("qin").hand) == 5
    assert table.seat("bar").hand == []
    assert table.seat("her").hand == []
    assert table.phase == "act"


def test_play_passes_counterclockwise():
    table = _ready()
    for seat in table.seats:
        seat.hand = ["loli:1", "girl:1"]
    table.turn = table.index("you")
    table.play(["loli:1"])
    assert table.seats[table.turn].id == "bar"
    table.play(["loli:1"])
    assert table.seats[table.turn].id == "her"
    table.play(["loli:1"])
    assert table.seats[table.turn].id == "qin"
    table.play(["loli:1"])
    assert table.seats[table.turn].id == "you"


def test_two_seated_players_must_call_the_last_hand():
    table = _ready()
    table.table = "lady"
    for seat in table.seats:
        seat.alive = seat.id in ("you", "qin")
        seat.hand = []
    table.seat("you").hand = ["girl:1"]
    table.seat("qin").hand = ["lady:1", "lady:2"]
    table.turn = table.index("you")
    table.play(["girl:1"])
    assert table.phase == "show"
    assert table.show["kind"] == "reveal"
    assert table.show["caller"] == "qin"
    assert table.show["actor"] == "you"
    assert table.show["honest"] is False
    assert table.show["shooter"] == "you"
    assert table.note["line"] == "只剩我们两个。揭穿。"
    assert table.seat("qin").hand == ["lady:1", "lady:2"]


def test_two_seated_players_can_still_follow_before_the_hand_is_empty():
    table = _ready()
    table.table = "lady"
    for seat in table.seats:
        seat.alive = seat.id in ("you", "qin")
        seat.hand = []
    table.seat("you").hand = ["lady:1", "lady:2"]
    table.seat("qin").hand = ["girl:1"]
    table.turn = table.index("you")
    table.play(["lady:1"])
    assert table.phase == "act"
    assert table.seats[table.turn].id == "qin"
    assert table.pile["actor"] == "you"


def test_finishers_score_by_empty_order_and_the_dead_score_by_death_order():
    table = _ready()
    table.finished = ["qin", "you"]
    table.aside = ["qin", "you"]
    table.fallen = ["her"]
    for seat in table.seats:
        seat.hand = []
        seat.alive = seat.id in ("qin", "you", "bar")
    table.phase = "show"
    table.show = {"kind": "clear", "who": "bar"}
    table.ack()
    by_id = {row["id"]: row for row in table.places}
    assert by_id["bar"]["tag"] == "win" and by_id["bar"]["points"] == 0 and by_id["bar"]["place"] == 1
    assert by_id["qin"]["tag"] == "finish" and by_id["qin"]["points"] == 50 and by_id["qin"]["rank"] == 1 and by_id["qin"]["place"] == 1
    assert by_id["you"]["tag"] == "finish" and by_id["you"]["points"] == 20 and by_id["you"]["rank"] == 2 and by_id["you"]["place"] == 1
    assert by_id["her"]["tag"] == "death" and by_id["her"]["points"] == -50 and by_id["her"]["rank"] == 1 and by_id["her"]["place"] == 4

    dead = _ready()
    dead.fallen = ["you", "qin", "bar"]
    for seat in dead.seats:
        seat.hand = []
        seat.alive = seat.id == "her"
    dead.phase = "show"
    dead.show = {"kind": "reveal", "hit": True, "shooter": "bar"}
    dead.ack()
    lost = {row["id"]: row["points"] for row in dead.places}
    assert lost["her"] == 0
    assert [lost[pid] for pid in ("you", "qin", "bar")] == [-50, -30, -10]


def test_the_other_deck_deals_the_three_male_suits():
    table = Table(her_name="清宵", rng=random.Random(1), deck="ink")
    table.start()
    faces = {face_of(card) for seat in table.seats for card in seat.hand}
    assert faces <= {"pup", "boy", "sire", "mei", "ying"}
    assert table.table in ("pup", "boy", "sire")
    assert table.view()["faces"] == ["pup", "boy", "sire"]
    table.phase = "name"
    table.turn = 0
    try:
        table.name("loli")
    except RuleError as exc:
        assert str(exc) == "face"
    else:
        raise AssertionError("rose suit")


def test_a_round_gives_each_ai_a_different_goal():
    from app.modules.tavern.rules import GOALS

    table = Table(her_name="清宵", rng=random.Random(2))
    table.start()
    goals = [table.seat(pid).goal for pid in ("qin", "bar", "her")]
    assert set(goals) <= set(GOALS)
    assert len(set(goals)) == 3
    assert table.seat("you").goal == ""
    table._roll_goals()
    again = [table.seat(pid).goal for pid in ("qin", "bar", "her")]
    assert len(set(again)) == 3
    assert set(again) <= set(GOALS)


def test_a_safe_goal_refuses_the_gun_and_a_push_goal_calls():
    from app.modules.tavern.rules import Seat, wants_call

    careful = Seat("qin", "ai", 0.1, 0.3, goal="scrape")
    careful.gun.pulls = 2
    assert wants_call(careful, 1, "lady", 1, 0.2) is False
    bold = Seat("bar", "ai", 0.1, 0.9, goal="push")
    assert wants_call(bold, 2, "lady", 1, 0.2) is True


def test_remembered_bluffs_make_a_call_more_likely():
    from app.modules.tavern.habits import describe, note_into, suspicion
    from app.modules.tavern.rules import Seat, wants_call

    seats: dict = {}
    for _ in range(4):
        note_into(seats, {"t": "reveal", "caller": "qin", "actor": "you", "honest": False})
    note_into(seats, {"t": "play", "who": "you", "follow": True})
    assert seats["you"]["bluffs"] == 4
    assert suspicion(seats)["you"] > 0
    text = describe(seats, "清宵")
    assert "KE" in text and "爱诈" in text
    bar = Seat("bar", "ai", 0.55, 0.34)
    assert wants_call(bar, 1, "lady", 1, 0) is False
    assert wants_call(bar, 1, "lady", 1, suspicion(seats)["you"]) is True


def test_the_first_player_to_empty_is_the_first_finisher():
    table = _ready()
    table.table = "lady"
    table.phase = "act"
    for seat in table.seats:
        seat.alive = True
    table.seat("bar").hand = ["lady:1"]
    table.seat("you").hand = ["lady:6"]
    table.seat("her").hand = ["lady:2", "lady:3"]
    table.seat("qin").hand = ["lady:4", "lady:5"]
    table.turn = table.index("bar")
    table.play(["lady:1"])
    table.play(["lady:2"])
    table.play(["lady:4"])
    table.play(["lady:6"])
    assert table.finished == ["bar", "you"]
    assert table.duel == ["her", "qin"]


def test_a_redeal_keeps_the_dead_out_when_two_are_still_seated():
    table = _ready()
    table.fallen = ["bar", "her"]
    for seat in table.seats:
        seat.alive = seat.id in ("you", "qin")
        seat.hand = []
    table.seat("bar").alive = True
    table.seat("bar").hand = ["loli:1"]
    table.phase = "show"
    table.show = {"kind": "clear", "who": "you"}
    table.ack()
    assert table.phase == "act"
    assert table.seat("you").alive is True and len(table.seat("you").hand) == 5
    assert table.seat("qin").alive is True and len(table.seat("qin").hand) == 5
    assert table.seat("bar").alive is False and table.seat("bar").hand == []
    assert table.seat("her").alive is False and table.seat("her").hand == []
    assert set(table.note["seated"]) == {"you", "qin"}
    assert table.note["dealt"] is True


def test_last_survivor_takes_the_table():
    table = _ready()
    for seat in table.seats:
        if seat.id != "her":
            seat.alive = False
    table.phase = "show"
    table.show = {"kind": "clear", "who": "her"}
    table.ack()
    assert table.phase == "over"
    assert table.winner == "her"


def test_random_tables_finish():
    for seed in range(8):
        rng = random.Random(seed)
        table = Table(her_name="她", rng=random.Random(seed))
        table.start()
        guard = 0
        while table.phase != "over" and guard < 500:
            guard += 1
            if table.phase == "show":
                table.ack()
                continue
            if not any(seat.hand for seat in table.seats if seat.alive):
                table.open_next()
                continue
            if table.phase == "name":
                if table.seats[table.turn].kind == "human":
                    table.name(rng.choice(("loli", "girl", "lady")))
                else:
                    table.step()
                continue
            seat = table.seats[table.turn]
            if seat.kind == "human":
                if table.pile and rng.random() < 0.4:
                    table.call()
                else:
                    n = 1 if len(seat.hand) == 1 or rng.random() < 0.65 else min(2, len(seat.hand))
                    table.play(seat.hand[:n])
            else:
                table.step()
        assert table.phase == "over", seed
        assert table.winner
        assert guard < 500
        assert any(row["id"] == table.winner and row["place"] == 1 and row["tag"] == "win" for row in table.places)
        assert all(row["place"] == 1 for row in table.places if row["tag"] in ("win", "finish"))
        assert all(row["place"] == 4 for row in table.places if row["tag"] == "death")
        assert all(row["points"] in (50, 20, 10, 0, -10, -30, -50) for row in table.places)

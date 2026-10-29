"""魅影酒馆的一桌。

二十张牌。给男性玩家的一副是萝莉、少女、御姐，给女性玩家的一副是犬系、正太、爹系，各六张。魅（大王）与影（小王）各一张，两副都有。
开局发牌。打出去的牌离开手牌，仪式之后不补。
手里出完的人轮空。有人中弹离席也不发牌，剩下的人继续用手里的牌。
只有还坐着的人自己把牌打光，才重新发。重新发只发给还坐着的人，离席的不会回来。
揭穿之后，进过仪式并且还坐着的人指定下一轮牌型；手里还有牌，就再出一到三张。
出牌按逆时针：KE 的下家是右边，然后对面，再左边。下家可以跟，也可以揭穿。场上只剩两个人还拿着牌时，上家打出最后一手，下家必须揭穿，不能再出牌。先出完牌的人不再回到这两个人的新局。
揭穿错了，揭的人开枪；揭对了，出牌的人开枪。
除了座位 you，其余三人的揭穿或跟牌交给模型。每一局三人各带一个不同的目标，再按局面分析决定跟还是揭穿；模型没给出合法一手时，才按这一局的目标退回。
最后两个人里有一个出完牌，仪式裁决完，就只在这两个人之间重发一局，不再让另一个人把剩下的牌打完。每人三膛一颗实弹，中弹离席，最后留下的人赢。
提前出完的人按先后加 50、20、10 分。离席的人按先后扣 50、30、10 分。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

CHAMBERS = 3
REAL = ("loli", "girl", "lady")
DECKS = {
    "rose": ("loli", "girl", "lady"),
    "ink": ("pup", "boy", "sire"),
}
GOALS = ("scrape", "safe", "push", "win", "read")
WILD = frozenset({"mei", "ying"})
COUNTS = {"loli": 6, "girl": 6, "lady": 6, "mei": 1, "ying": 1}


class RuleError(ValueError):
    """前端按这个短码自己翻译。"""


def face_of(card: str) -> str:
    return card.split(":", 1)[0]


def honest(card: str, table: str) -> bool:
    face = face_of(card)
    return face == table or face in WILD


def build_deck(deck: str = "rose") -> list[str]:
    faces = DECKS.get(deck, DECKS["rose"])
    counts = {face: 6 for face in faces}
    counts["mei"] = 1
    counts["ying"] = 1
    out: list[str] = []
    for face, count in counts.items():
        for i in range(1, count + 1):
            out.append(f"{face}:{i}")
    return out


@dataclass
class Gun:
    bullet: int
    pulls: int = 0

    def fire(self) -> bool:
        hit = self.pulls == self.bullet
        self.pulls += 1
        return hit


@dataclass
class Seat:
    id: str
    kind: str
    bluff: float
    call_at: float
    hand: list[str] = field(default_factory=list)
    gun: Gun = field(default_factory=lambda: Gun(0))
    alive: bool = True
    goal: str = ""


def goal_bluff(goal: str) -> float:
    return {"scrape": 0.06, "safe": 0.16, "push": 0.7, "win": 0.38, "read": 0.28}.get(goal, 0.25)


def goal_threshold(seat: Seat, suspicion: float) -> float:
    """目标给倾向，局面分析改这条线。枪快空了就收，对方爱诈才更敢揭。"""
    if not seat.goal:
        return seat.call_at
    base = {"scrape": 0.74, "safe": 0.58, "push": 0.3, "win": 0.46, "read": 0.5}[seat.goal]
    if seat.gun.pulls >= 2 and seat.goal in ("scrape", "safe", "win"):
        base += 0.22
    elif seat.gun.pulls == 0 and seat.goal in ("push", "win"):
        base -= 0.06
    if suspicion > 0.12 and seat.goal in ("read", "win", "push", "safe"):
        base -= 0.1
    elif suspicion < -0.08 and seat.goal in ("read", "safe", "win"):
        base += 0.1
    return base


def wants_call(seat: Seat, pile_n: int, table: str, pressure: int, suspicion: float = 0) -> bool:
    """手里真话越多，别人越像在撒谎。局数越深，越敢揭。suspicion 来自这个人以往的诈。"""
    mine = sum(1 for card in seat.hand if honest(card, table))
    score = 0.20 + 0.22 * (pile_n - 1) + 0.08 * mine + min(pressure, 6) * 0.03 + suspicion
    if pile_n >= 3:
        score += 0.22
    return score >= goal_threshold(seat, suspicion)


def choose_suit(seat: Seat, rng: random.Random, faces: tuple[str, ...] = REAL) -> str:
    """仪式之后，尽量指定自己手里最多的那一种。"""
    counts = {face: sum(1 for card in seat.hand if face_of(card) == face) for face in faces}
    best = max(counts.values())
    options = [face for face, count in counts.items() if count == best]
    return rng.choice(options)


def choose_play(seat: Seat, table: str, rng: random.Random) -> list[str]:
    good = [card for card in seat.hand if honest(card, table)]
    fake = [card for card in seat.hand if card not in good]
    if not seat.hand:
        raise RuleError("empty")
    bluff = goal_bluff(seat.goal) if seat.goal else seat.bluff
    if seat.goal == "scrape" and good:
        return good[:1]
    if seat.goal == "win" and good and len(seat.hand) <= 3 and rng.random() < 0.65:
        return good[: min(3, len(good))]
    if not good:
        n = 1 if len(fake) == 1 or rng.random() < 0.7 else min(2, len(fake))
        return fake[:n]
    if fake and rng.random() < bluff:
        play = [fake[0]]
        if rng.random() < 0.55:
            play.append(good[0])
        return play
    n = 1
    if len(good) >= 2 and rng.random() < 0.5:
        n = 2
    if len(good) >= 3 and rng.random() < 0.18:
        n = 3
    return good[:n]


_FACE_ZH = {
    "loli": "萝莉",
    "girl": "少女",
    "lady": "御姐",
    "pup": "犬系",
    "boy": "正太",
    "sire": "爹系",
}
_COUNT_ZH = {1: "一张", 2: "两张", 3: "三张"}


def _fallback_play(seat: Seat, table: str, n: int, follow: bool) -> str:
    del seat
    face = _FACE_ZH.get(table, "这张")
    count = _COUNT_ZH.get(n, f"{n}张")
    if follow:
        return f"我跟。{count}{face}。"
    return f"我先出。{count}{face}。"


def _fallback_call(seat: Seat) -> str:
    del seat
    return "揭穿。我不信。"


def _fallback_name(seat: Seat, face: str) -> str:
    label = _FACE_ZH.get(face, face)
    if seat.id == "qin":
        return f"那就{label}。"
    if seat.id == "bar":
        return f"这一轮，{label}。"
    return f"我定{label}。"


class Table:
    def __init__(self, her_name: str = "她", rng: random.Random | None = None, deck: str = "rose") -> None:
        self.rng = rng or random.Random()
        self.her_name = (her_name or "她").strip()[:24] or "她"
        self.deck = deck if deck in DECKS else "rose"
        self.faces = DECKS[self.deck]
        # 逆时针：KE（下）→ AI（右）→ 对面 → XiaO（左）→ KE。
        self.seats = [
            Seat("you", "human", 0.0, 1.0),
            Seat("bar", "ai", 0.55, 0.34),
            Seat("her", "ai", 0.28, 0.48),
            Seat("qin", "ai", 0.10, 0.62),
        ]
        self.phase = "idle"
        self.table = ""
        self.pile: dict | None = None
        self.show: dict | None = None
        self.turn = 0
        self.dealer = 0
        self.round_no = 0
        self.winner = ""
        self.seq = 0
        self.fallen: list[str] = []
        self.duel: list[str] = []
        self.aside: list[str] = []
        self.emptied: list[str] = []
        self.finished: list[str] = []
        self.places: list[dict] = []
        self.paid = False
        self.coin_delta = 0
        self.night = 0
        self.memory: dict[str, float] = {}
        self.note: dict = {"seq": 0, "t": "idle"}

    def index(self, pid: str) -> int:
        for i, seat in enumerate(self.seats):
            if seat.id == pid:
                return i
        raise RuleError("who")

    def seat(self, pid: str) -> Seat:
        return self.seats[self.index(pid)]

    def _mark(self, **payload) -> None:
        self.seq += 1
        self.note = {"seq": self.seq, **payload}

    def _living_at(self, idx: int) -> int:
        n = len(self.seats)
        for step in range(n):
            j = (idx + step) % n
            if self.seats[j].alive:
                return j
        raise RuleError("empty")

    def _next_with_cards(self, idx: int) -> int | None:
        n = len(self.seats)
        for step in range(1, n):
            j = (idx + step) % n
            seat = self.seats[j]
            if seat.alive and seat.hand:
                return j
        return None

    def start(self) -> None:
        for seat in self.seats:
            seat.alive = True
            seat.hand = []
            seat.gun = Gun(self.rng.randrange(CHAMBERS))
        self.winner = ""
        self.fallen = []
        self.duel = []
        self.aside = []
        self.emptied = []
        self.finished = []
        self.places = []
        self.paid = False
        self.coin_delta = 0
        self.night = time.time_ns()
        self.memory = {}
        self.round_no = 0
        self.dealer = self.rng.randrange(len(self.seats))
        self._open_round("")

    def _bury(self) -> None:
        """离席的人离开这一轮。手牌清掉，不能再被发回来。"""
        for seat in self.seats:
            if seat.id in self.fallen:
                seat.alive = False
                seat.hand = []

    def _lock_duel(self) -> None:
        """还拿着牌的只剩两个时，新局就只在这两个人之间。

        已经出完的、已经离席的，都不再发回来。
        """
        if self.duel:
            return
        alive = [seat for seat in self.seats if seat.alive and seat.id not in self.aside]
        holders = [seat for seat in alive if seat.hand]
        if len(alive) == 2:
            self.duel = [seat.id for seat in alive]
            return
        if len(holders) != 2 or len(alive) <= 2:
            return
        self.duel = [seat.id for seat in holders]
        waiting = [seat.id for seat in alive if seat.id not in self.duel and seat.id not in self.aside]
        waiting.sort(key=lambda pid: self.emptied.index(pid) if pid in self.emptied else len(self.emptied))
        for pid in waiting:
            self.aside.append(pid)
            if pid not in self.finished:
                self.finished.append(pid)

    def _still_in(self) -> list[Seat]:
        if self.duel:
            return [seat for seat in self.seats if seat.alive and seat.id in self.duel]
        return [seat for seat in self.seats if seat.alive and seat.id not in self.aside]

    def _deal(self) -> bool:
        """只发给这一局还在打的人。离席的、已经出完的，都不发。"""
        self._bury()
        self._lock_duel()
        living = self._still_in()
        if len(living) <= 1:
            self._crown(living[0].id if living else "")
            return False
        deck = build_deck(self.deck)
        self.rng.shuffle(deck)
        per = min(5, len(deck) // len(living))
        for seat in self.seats:
            seat.hand = []
        for seat in living:
            if seat.id in self.emptied:
                self.emptied.remove(seat.id)
            seat.hand = [deck.pop() for _ in range(per)]
        self.pile = None
        self.show = None
        self.round_no += 1
        return True

    def _open_round(self, namer: str, deal_if_empty: bool = True) -> None:
        """手里还有牌就不发。中弹离席也不发。

        只有这一轮的牌是自己打光的，才重新发。
        仪式后还坐着的人指定牌型。中弹离席，或开局，桌牌由系统指定。
        """
        self._bury()
        self._lock_duel()
        dealt = False
        if not any(seat.hand for seat in self.seats if seat.alive):
            if not deal_if_empty:
                self.pile = None
                self.show = None
                self.phase = "act"
                self.turn = self._living_at(self.dealer)
                self._mark(t="spent", who=self.seats[self.turn].id)
                return
            if not self._deal():
                return
            dealt = True
        else:
            self.pile = None
            self.show = None
        seat = self.seat(namer) if namer else None
        if seat and seat.alive:
            self.table = ""
            self.phase = "name"
            self.turn = self.index(seat.id)
            self._roll_goals()
            self._mark(t="rite", who=seat.id)
            return
        self.table = self.rng.choice(self.faces)
        self.phase = "act"
        opener = self._first_with_cards(self.dealer)
        self.turn = opener if opener is not None else self._living_at(self.dealer)
        self.dealer = (self.turn + 1) % len(self.seats)
        seated = [seat.id for seat in self._still_in()]
        self._roll_goals()
        self._mark(t="deal", face=self.table, who=self.seats[self.turn].id, seated=seated, dealt=dealt)

    def _first_with_cards(self, idx: int) -> int | None:
        n = len(self.seats)
        for step in range(n):
            j = (idx + step) % n
            seat = self.seats[j]
            if seat.alive and seat.hand:
                return j
        return None

    def name(self, face: str) -> None:
        if self.phase != "name":
            raise RuleError("wait")
        if face not in self.faces:
            raise RuleError("face")
        seat = self.seats[self.turn]
        if not seat.alive:
            raise RuleError("turn")
        self.table = face
        self.phase = "act"
        if not seat.hand:
            nxt = self._next_with_cards(self.turn)
            if nxt is None:
                raise RuleError("empty")
            self.turn = nxt
        self._mark(t="name", face=face, who=seat.id)

    def _require_act(self) -> Seat:
        if self.phase != "act":
            raise RuleError("wait")
        seat = self.seats[self.turn]
        if not seat.alive:
            raise RuleError("turn")
        return seat

    def play(self, ids: list[str]) -> None:
        seat = self._require_act()
        if len(ids) != len(set(ids)) or not 1 <= len(ids) <= 3:
            raise RuleError("count")
        if any(card not in seat.hand for card in ids):
            raise RuleError("missing")
        followed = self.pile is not None
        for card in ids:
            seat.hand.remove(card)
        if not seat.hand:
            self._remember_empty(seat.id)
        self.pile = {"actor": seat.id, "cards": list(ids)}
        self._lock_duel()
        holders = [other for other in self.seats if other.alive and other.hand and other.id != seat.id]
        if not seat.hand and len(holders) == 1:
            other = holders[0]
            self.turn = self.index(other.id)
            self.call()
            self.note["line"] = "只剩我们两个。揭穿。"
            return
        nxt = self._next_with_cards(self.turn)
        if nxt is None:
            self.phase = "show"
            self.show = {"kind": "clear", "who": seat.id}
            self.pile = None
            self._mark(t="clear", who=seat.id)
            return
        self.turn = nxt
        self._mark(t="play", who=seat.id, n=len(ids), follow=followed)

    def call(self) -> None:
        caller = self._require_act()
        if not self.pile:
            raise RuleError("nocall")
        actor = self.seat(self.pile["actor"])
        cards = list(self.pile["cards"])
        ok = all(honest(card, self.table) for card in cards)
        loser = caller if ok else actor
        hit = loser.gun.fire()
        if hit:
            loser.alive = False
            loser.hand = []
            if loser.id not in self.fallen:
                self.fallen.append(loser.id)
            if loser.id in self.emptied and loser.id not in self.finished:
                self.emptied.remove(loser.id)
        self.pile = None
        self.phase = "show"
        self.show = {
            "kind": "reveal",
            "actor": actor.id,
            "caller": caller.id,
            "cards": list(cards),
            "honest": ok,
            "shooter": loser.id,
            "hit": hit,
        }
        self._mark(
            t="reveal",
            actor=actor.id,
            caller=caller.id,
            cards=self.show["cards"],
            honest=ok,
            shooter=loser.id,
            hit=hit,
        )

    def ack(self) -> None:
        if self.phase != "show":
            raise RuleError("wait")
        self._bury()
        self._lock_duel()
        living = self._still_in()
        if len(living) <= 1:
            self._crown(living[0].id if living else "")
            return
        hit = bool(self.show and self.show.get("hit"))
        fresh = (
            bool(self.duel)
            and len(living) == 2
            and bool(self.show and self.show.get("kind") == "reveal")
            and not hit
            and any(not seat.hand for seat in living)
        )
        if fresh:
            for seat in living:
                seat.hand = []
            self._open_round("", deal_if_empty=True)
            return
        namer = ""
        if self.show and self.show.get("kind") == "reveal" and not hit:
            namer = str(self.show.get("shooter") or "")
        self._open_round(namer, deal_if_empty=not hit)

    def open_next(self) -> None:
        """桌上已经没牌，而且不是中弹当场补的。由玩家决定再发一轮。"""
        self._bury()
        self._lock_duel()
        living = self._still_in()
        if len(living) <= 1:
            self._crown(living[0].id if living else "")
            return
        if any(seat.hand for seat in living):
            raise RuleError("wait")
        self._open_round("")

    def _roll_goals(self) -> None:
        """这一局还在打的人，各拿一个不同的目标。下一局再换。"""
        living = [
            seat for seat in self.seats
            if seat.kind == "ai" and seat.alive and seat.id not in self.aside and (not self.duel or seat.id in self.duel)
        ]
        bag = list(GOALS)
        self.rng.shuffle(bag)
        playing = {seat.id for seat in living}
        for seat in self.seats:
            if seat.id not in playing:
                seat.goal = ""
        for seat, goal in zip(living, bag):
            seat.goal = goal

    def brief(self) -> dict:
        """给模型的公开局面。只有当前这个人的手牌，没有别人的牌，也没有子弹在第几膛。"""
        seat = self.seats[self.turn]
        return {
            "phase": self.phase,
            "who": seat.id,
            "table": self.table,
            "hand": list(seat.hand),
            "pile": None if not self.pile else {"actor": self.pile["actor"], "n": len(self.pile["cards"])},
            "pulls": seat.gun.pulls,
            "goal": seat.goal,
            "deck": self.deck,
            "faces": list(self.faces),
            "round": self.round_no,
            "her_name": self.her_name,
            "seats": [
                {
                    "id": other.id,
                    "alive": other.alive,
                    "cards": len(other.hand),
                    "pulls": other.gun.pulls,
                    "out": other.id in self.aside,
                }
                for other in self.seats
            ],
        }

    def step(self, decision: dict | None = None) -> None:
        if not any(seat.hand for seat in self.seats if seat.alive):
            raise RuleError("spent")
        if self.phase == "name":
            seat = self.seats[self.turn]
            if seat.kind == "human":
                raise RuleError("turn")
            face = str((decision or {}).get("face") or "")
            if face not in self.faces:
                face = choose_suit(seat, self.rng, self.faces)
            self.name(face)
            self._say(decision, _fallback_name(seat, self.table))
            return
        seat = self._require_act()
        if seat.kind == "human":
            raise RuleError("turn")
        act = str((decision or {}).get("act") or "")
        cards = [str(card) for card in ((decision or {}).get("cards") or [])]
        if act == "call" and self.pile:
            self.call()
            self._say(decision, _fallback_call(seat))
            return
        if act == "play" and self._legal(seat, cards):
            self.play(cards)
            if self.note.get("t") != "reveal":
                self._say(decision, _fallback_play(seat, self.table, len(cards), bool(self.note.get("follow"))))
            return
        suspicion = float(self.memory.get(str(self.pile["actor"])) or 0) if self.pile else 0
        if self.pile and wants_call(seat, len(self.pile["cards"]), self.table, self.round_no, suspicion):
            self.call()
            self._say(None, _fallback_call(seat))
            return
        played = choose_play(seat, self.table, self.rng)
        self.play(played)
        if self.note.get("t") != "reveal":
            self._say(None, _fallback_play(seat, self.table, len(played), bool(self.note.get("follow"))))

    def _remember_empty(self, pid: str) -> None:
        if pid in self.fallen or pid in self.finished or pid in self.emptied:
            return
        self.emptied.append(pid)

    def _crown(self, winner: str) -> None:
        """提前出完按先后加 50、20、10。离席按先后扣 50、30、10。活下来的人和提前出完的人都算胜利。"""
        self.phase = "over"
        self.show = None
        self.pile = None
        self.winner = winner
        finish_points = (50, 20, 10)
        death_points = (-50, -30, -10)
        places: list[dict] = []
        seen: set[str] = set()
        if winner:
            places.append({"id": winner, "place": 1, "points": 0, "tag": "win", "rank": 1})
            seen.add(winner)
        finishers = [pid for pid in self.finished if pid not in seen and pid not in self.fallen]
        for i, pid in enumerate(finishers):
            places.append({
                "id": pid,
                "place": 1,
                "points": finish_points[i] if i < len(finish_points) else 0,
                "tag": "finish",
                "rank": i + 1,
            })
            seen.add(pid)
        for i, pid in enumerate(self.fallen):
            if pid in seen:
                continue
            places.append({
                "id": pid,
                "place": 4,
                "points": death_points[i] if i < len(death_points) else 0,
                "tag": "death",
                "rank": i + 1,
            })
            seen.add(pid)
        self.places = places
        self._mark(t="win", who=winner)

    def _say(self, decision: dict | None, fallback: str) -> None:
        raw = str((decision or {}).get("line") or "")
        cleaned = " ".join("".join(ch for ch in raw if ch not in "{}\"[]`").split())
        self.note["line"] = (cleaned[:22] or fallback)

    def _legal(self, seat: Seat, cards: list[str]) -> bool:
        return bool(cards) and len(cards) == len(set(cards)) and 1 <= len(cards) <= 3 and all(card in seat.hand for card in cards)

    def view(self) -> dict:
        you = self.seat("you")
        return {
            "phase": self.phase,
            "table": self.table,
            "turn": self.seats[self.turn].id if self.phase in ("act", "name") else "",
            "winner": self.winner,
            "places": list(self.places),
            "her_name": self.her_name,
            "deck": self.deck,
            "faces": list(self.faces),
            "round": self.round_no,
            "pile": None if not self.pile else {"actor": self.pile["actor"], "n": len(self.pile["cards"])},
            "show": self.show,
            "note": self.note,
            "you": {
                "alive": you.alive,
                "pulls": you.gun.pulls,
                "hand": [{"id": card, "face": face_of(card)} for card in you.hand],
            },
            "seats": [
                {
                    "id": seat.id,
                    "alive": seat.alive,
                    "cards": len(seat.hand),
                    "pulls": seat.gun.pulls,
                    "out": seat.id in self.aside,
                    "finish": (self.finished.index(seat.id) + 1) if seat.id in self.finished else 0,
                }
                for seat in self.seats
            ],
        }

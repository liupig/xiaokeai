"""陪看截图落盘。不调用视觉模型。"""
import base64
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.modules.glance import archive, trace


def _use(root: Path, packed: bool = False) -> None:
    archive.bind(root, packed=packed)
    trace.clear()


def _shot(text: str = "船在海上") -> str:
    blob = base64.b64encode(b"jpeg-bytes").decode("ascii")
    return trace.note_look(
        {"ok": True, "text": text, "channel": "minicpm", "ms": 10},
        {"captured": [blob], "sent": [blob], "prompt": "看一眼"},
    )


def test_local_defaults_on_and_pack_defaults_off():
    with TemporaryDirectory() as raw:
        root = Path(raw)
        _use(root, packed=False)
        assert archive.keeping() is True
        assert archive.status()["days"] == 3
    with TemporaryDirectory() as raw:
        root = Path(raw)
        _use(root, packed=True)
        assert archive.keeping() is False
        archive.set_keeping(True)
        assert archive.keeping() is True
        archive.set_keeping(False)
        assert archive.keeping() is False


def test_screens_stay_on_disk_and_page_through_all():
    with TemporaryDirectory() as raw:
        root = Path(raw)
        _use(root, packed=False)
        first = _shot("船在海上")
        second = _shot("他推开了舱门")
        trace.mark(second, handoff="舱门", xiaoke_action="speak")
        latest = trace.feed(limit=1)
        assert latest["total"] == 2
        assert latest["has_older"] is True
        assert latest["items"][0]["id"] == second
        assert latest["items"][0]["handoff"] == "舱门"
        older = trace.feed(limit=1, before=second)
        assert older["items"][0]["id"] == first
        assert trace.shot(first, "captured", 0) == b"jpeg-bytes"
        trace._rows.clear()
        archive._rows = None
        again = trace.feed(limit=10)
        assert [row["id"] for row in again["items"]] == [second, first]
        assert again["items"][0]["handoff"] == "舱门"
        assert trace.shot(second, "sent", 0) == b"jpeg-bytes"


def test_switch_off_does_not_write_files():
    with TemporaryDirectory() as raw:
        root = Path(raw)
        _use(root, packed=True)
        item_id = _shot("不落盘")
        assert list(root.rglob("*.jpg")) == []
        page = trace.feed(limit=10)
        assert page["keeping"] is False
        assert page["items"][0]["id"] == item_id
        assert trace.shot(item_id, "captured", 0) == b"jpeg-bytes"


def test_prune_keeps_three_calendar_days():
    with TemporaryDirectory() as raw:
        root = Path(raw)
        _use(root, packed=False)
        today = date.today()
        keep = (today - timedelta(days=2)).isoformat()
        drop = (today - timedelta(days=3)).isoformat()
        for day in (keep, drop):
            folder = root / day
            folder.mkdir()
            (folder / "marker.txt").write_text("x", encoding="utf-8")
        archive.prune()
        assert (root / keep).is_dir()
        assert not (root / drop).exists()

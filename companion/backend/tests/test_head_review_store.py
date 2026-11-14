import json

from app.services import head_review_store


def test_head_review_samples(tmp_path, monkeypatch):
    path = tmp_path / "head_auto_review.json"
    monkeypatch.setattr(head_review_store, "FILE_PATH", path)
    head_review_store.save_motion({
        "name": "dance.vmd",
        "label": "舞蹈",
        "samples": [{"combo_id": "a", "ratio": 0.125, "verdict": "ok"}],
    })
    head_review_store.save_motion({
        "name": "walk.vmd",
        "label": "走路",
        "samples": [{"combo_id": "b", "ratio": 0.2, "verdict": "bad"}],
    })
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["motions"]["dance.vmd"]["samples"]["a"]["ratio"] == 0.125
    assert data["motions"]["walk.vmd"]["samples"]["b"]["verdict"] == "bad"
    assert not path.with_suffix(".json.tmp").exists()

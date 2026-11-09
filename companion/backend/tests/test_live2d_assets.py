import json
from pathlib import Path

from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.services import catalog
from app.services.extractor import classify_extracted
from app.services.live2d_assets import normalize_live2d_model


def test_classify_live2d_model_package(tmp_path: Path):
    model = tmp_path / "Haru" / "Haru.model3.json"
    model.parent.mkdir()
    model.write_text("{}")
    (model.parent / "Haru.moc3").write_bytes(b"moc")
    (model.parent / "texture.png").write_bytes(b"png")

    info = classify_extracted(tmp_path)

    assert info["model"] == model
    assert info["motions"] == []


def test_register_live2d_model(tmp_path: Path, monkeypatch):
    models = tmp_path / "models"
    model = models / "Haru" / "Haru.model3.json"
    model.parent.mkdir(parents=True)
    model.write_text("{}")
    monkeypatch.setattr(catalog, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(catalog, "MODELS_DIR", models)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        asset = catalog.register_model(session, model)
        session.add(asset)
        session.commit()
        session.refresh(asset)

        assert asset.name == "Haru"
        assert asset.fmt == "model3"
        assert asset.path == "models/Haru/Haru.model3.json"

        model.write_text('{"FileReferences": {}}')
        existing = catalog.register_model(session, model)
        session.commit()
        session.refresh(asset)
        assert existing.id == asset.id
        assert asset.size == model.stat().st_size


def test_normalize_merges_vtube_hotkeys_and_idle_animations(tmp_path: Path):
    model = tmp_path / "Haru.model3.json"
    model.write_text(json.dumps({
        "Version": 3,
        "FileReferences": {"Moc": "Haru.moc3", "Textures": []},
    }))
    (tmp_path / "Exp3").mkdir()
    (tmp_path / "Animation").mkdir()
    (tmp_path / "Exp3" / "blush.exp3.json").write_text("{}")
    for name in ("IDLE.motion3.json", "lost.motion3.json", "wave.motion3.json"):
        (tmp_path / "Animation" / name).write_text('{"Meta": {"Loop": true}}')
    (tmp_path / "Haru.vtube.json").write_text(json.dumps({
        "FileReferences": {
            "IdleAnimation": "IDLE.motion3.json",
            "IdleAnimationWhenTrackingLost": "lost.motion3.json",
        },
        "Hotkeys": [
            {"Name": "Blush", "Action": "ToggleExpression", "File": "blush.exp3.json"},
            {"Name": "Wave", "Action": "TriggerAnimation", "File": "wave.motion3.json"},
            {"Name": "Reset", "Action": "RemoveAllExpressions", "File": ""},
        ],
    }))

    report = normalize_live2d_model(model)

    assert report == {"textures_resized": 0, "expressions_added": 1, "motions_added": 3}
    refs = json.loads(model.read_text())["FileReferences"]
    assert refs["Expressions"] == [{"Name": "Blush", "File": "Exp3/blush.exp3.json"}]
    assert refs["Motions"]["Idle"][0]["File"] == "Animation/IDLE.motion3.json"
    assert refs["Motions"]["TrackingLost"][0]["File"] == "Animation/lost.motion3.json"
    assert refs["Motions"]["Wave"][0]["File"] == "Animation/wave.motion3.json"
    assert json.loads((tmp_path / "Animation" / "wave.motion3.json").read_text())["Meta"]["Loop"] is False
    assert json.loads((tmp_path / "Animation" / "IDLE.motion3.json").read_text())["Meta"]["Loop"] is True

    assert normalize_live2d_model(model) == {
        "textures_resized": 0, "expressions_added": 0, "motions_added": 0,
    }
    refs = json.loads(model.read_text())["FileReferences"]
    assert len(refs["Expressions"]) == 1
    assert sum(map(len, refs["Motions"].values())) == 3


def test_normalize_preserves_existing_declarations(tmp_path: Path):
    model = tmp_path / "Haru.model3.json"
    model.write_text(json.dumps({"FileReferences": {
        "Expressions": [{"Name": "Existing", "File": "Exp3/blush.exp3.json"}],
        "Motions": {"Existing": [{"File": "Animation/wave.motion3.json"}]},
    }}))
    (tmp_path / "Exp3").mkdir()
    (tmp_path / "Animation").mkdir()
    (tmp_path / "Exp3" / "blush.exp3.json").write_text("{}")
    (tmp_path / "Animation" / "wave.motion3.json").write_text("{}")
    (tmp_path / "Haru.vtube.json").write_text(json.dumps({"Hotkeys": [
        {"Name": "Duplicate", "Action": "ToggleExpression", "File": "blush.exp3.json"},
        {"Name": "Duplicate", "Action": "TriggerAnimation", "File": "wave.motion3.json"},
    ]}))

    assert normalize_live2d_model(model)["expressions_added"] == 0
    assert normalize_live2d_model(model)["motions_added"] == 0
    refs = json.loads(model.read_text())["FileReferences"]
    assert refs["Expressions"][0]["Name"] == "Existing"
    assert list(refs["Motions"]) == ["Existing"]


def test_normalize_downscales_only_oversized_referenced_textures(tmp_path: Path):
    large = tmp_path / "large.png"
    small = tmp_path / "small.png"
    Image.new("RGBA", (5000, 1000)).save(large)
    Image.new("RGBA", (1024, 512)).save(small)
    model = tmp_path / "Haru.model3.json"
    model.write_text(json.dumps({"FileReferences": {"Textures": ["large.png", "small.png"]}}))

    report = normalize_live2d_model(model)

    assert report["textures_resized"] == 1
    with Image.open(large) as image:
        assert image.size == (5000, 1000)
    with Image.open(tmp_path / "large.max4096.png") as image:
        assert image.size == (4096, 819)
    with Image.open(small) as image:
        assert image.size == (1024, 512)
    refs = json.loads(model.read_text())["FileReferences"]
    assert refs["Textures"] == ["large.max4096.png", "small.png"]
    assert normalize_live2d_model(model)["textures_resized"] == 0

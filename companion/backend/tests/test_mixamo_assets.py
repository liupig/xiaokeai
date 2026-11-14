import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

from app.models import Asset
from app.routers.assets import update_asset
from app.services import catalog, importer, motion_review_store
from app.services.extractor import sniff_kind


def test_sniff_mixamo_binary(tmp_path: Path):
    fbx = tmp_path / "motion.fbx"
    fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00")
    assert sniff_kind(fbx) == ".fbx"


def test_import_single_mixamo_motion(tmp_path: Path, monkeypatch):
    assets = tmp_path / "assets"
    motions = assets / "motions"
    motions.mkdir(parents=True)
    monkeypatch.setattr(catalog, "ASSETS_DIR", assets)
    monkeypatch.setattr(importer, "MOTIONS_DIR", motions)
    source = tmp_path / "wave.fbx"
    source.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00motion")
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = importer.import_downloaded(session, source)

    assert len(created) == 1
    motion = created[0]
    assert motion.kind == "motion"
    assert motion.fmt == "fbx"
    assert motion.path == "motions/wave.fbx"
    assert motion.label == "[打招呼] 挥手（Mixamo）"
    assert (motions / "wave.fbx").is_file()


def test_import_xiaoke_motion(tmp_path: Path, monkeypatch):
    assets = tmp_path / "assets"
    motions = assets / "motions"
    motions.mkdir(parents=True)
    monkeypatch.setattr(catalog, "ASSETS_DIR", assets)
    monkeypatch.setattr(importer, "MOTIONS_DIR", motions)
    source = tmp_path / "walk-unarmed-forward.xkmotion"
    source.write_text('{"format":"xiaoke-motion","version":1,"rig":"pmx","clip":{}}')
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = importer.import_downloaded(session, source)

    assert len(created) == 1
    motion = created[0]
    assert motion.fmt == "xkmotion"
    assert motion.path == "motions/walk-unarmed-forward.xkmotion"
    assert motion.label == "[互动] 向前走（Mixamo）"
    assert (motions / "walk-unarmed-forward.xkmotion").is_file()


def test_motion_review_status(tmp_path: Path, monkeypatch):
    backup = tmp_path / "motion_review.json"
    monkeypatch.setattr(motion_review_store, "FILE_PATH", backup)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        asset = Asset(kind="motion", name="wave.vmd", meta='{"category":"greet"}')
        session.add(asset)
        session.commit()
        session.refresh(asset)

        updated = update_asset(asset.id, {"review_status": "rejected"}, session)
        assert json.loads(updated.meta) == {"category": "greet", "review_status": "rejected"}
        saved = json.loads(backup.read_text(encoding="utf-8"))
        assert saved["summary"] == {"total": 1, "approved": 0, "rejected": 1, "pending": 0}
        assert saved["motions"][0]["name"] == "wave.vmd"
        assert saved["motions"][0]["review_status"] == "rejected"
        assert not backup.with_suffix(".json.tmp").exists()

        with pytest.raises(HTTPException) as exc_info:
            update_asset(asset.id, {"review_status": "invalid"}, session)
        assert exc_info.value.status_code == 400
        assert json.loads(updated.meta)["review_status"] == "rejected"


def test_manifest_category(tmp_path: Path):
    pack = tmp_path / "xiaokeai-mixamo"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        '{"motions":[{"file":"Thankful.vmd","category":"interact"}]}',
        encoding="utf-8",
    )
    assert catalog.manifest_category(pack / "Thankful.vmd") == "interact"
    assert catalog.manifest_category(pack / "Missing.vmd") == ""
    assert catalog.manifest_category(tmp_path / "Other.vmd") == ""

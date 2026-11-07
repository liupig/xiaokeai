from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.services import catalog
from app.services.extractor import classify_extracted


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

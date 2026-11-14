import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..models import Asset
from ..paths import DATA_DIR

FILE_PATH = DATA_DIR / "motion_review.json"


def export_review(session: Session):
    assets = session.exec(select(Asset).where(Asset.kind == "motion").order_by(Asset.id)).all()
    motions = []
    summary = {"total": 0, "approved": 0, "rejected": 0, "pending": 0}
    for asset in assets:
        try:
            status = json.loads(asset.meta or "{}").get("review_status", "pending")
        except json.JSONDecodeError:
            status = "pending"
        if status not in ("approved", "rejected", "pending"):
            status = "pending"
        summary["total"] += 1
        summary[status] += 1
        motions.append({
            "id": asset.id,
            "name": asset.name,
            "label": asset.label,
            "path": asset.path,
            "review_status": status,
        })
    data = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "motions": motions,
    }
    FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE_PATH.with_suffix(FILE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(FILE_PATH)
    return data

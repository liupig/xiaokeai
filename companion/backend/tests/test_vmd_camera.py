"""镜头 VMD 生成 / 识别。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vmd_camera import (  # noqa: E402
    BUILTINS,
    RETIRED_BUILTIN_FILES,
    build_camera_vmd,
    inspect_vmd,
    is_camera_vmd,
    prune_retired_builtin_files,
    write_builtin_cameras,
)


def test_inspect_generated(tmp: Path) -> None:
    dest = tmp / "cams"
    written = write_builtin_cameras(dest)
    assert written, "应写出内置运镜"
    labels = {s["label"] for s in BUILTINS}
    assert labels == {"左侧环绕", "右侧环绕", "环绕一周", "螺旋一周", "弧线扫过"}
    for p in dest.glob("*.vmd"):
        info = inspect_vmd(p)
        assert info["cameras"] > 0
        assert info["bones"] == 0
        assert is_camera_vmd(p)
        assert p.name not in RETIRED_BUILTIN_FILES


def test_prune_retired(tmp: Path) -> None:
    dest = tmp / "stale"
    dest.mkdir()
    stale = dest / "cam-full.vmd"
    stale.write_bytes(b"x")
    removed = prune_retired_builtin_files(dest)
    assert stale in removed
    assert not stale.exists()


def test_build_roundtrip(tmp: Path) -> None:
    data = build_camera_vmd([
        (0, -20.0, (0.0, 14.0, 0.0), (0.0, 0.0, 0.0), 30),
        (30, -20.0, (0.0, 14.0, 0.0), (0.0, 0.4, 0.0), 30),
    ])
    p = tmp / "one.vmd"
    p.write_bytes(data)
    info = inspect_vmd(p)
    assert info == {"bones": 0, "morphs": 0, "cameras": 2}
    assert is_camera_vmd(p, "随意名字")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        test_inspect_generated(root)
        test_prune_retired(root)
        test_build_roundtrip(root)
        print("ok")

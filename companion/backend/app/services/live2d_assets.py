"""Normalize Live2D packages for the browser runtime."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PIL import Image

MAX_TEXTURE_SIZE = 4096


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _inside(root: Path, path: Path) -> bool:
    root = root.resolve()
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _vtube_file(model_path: Path) -> Optional[Path]:
    exact = model_path.with_name(f"{model_path.stem}.vtube.json")
    if exact.is_file():
        return exact
    candidates = sorted(model_path.parent.glob("*.vtube.json"))
    return candidates[0] if len(candidates) == 1 else None


def _resource_resolver(model_dir: Path):
    indexed = {
        p.name.lower(): p
        for p in sorted(model_dir.rglob("*")) if p.is_file()
    }

    def resolve(name: str) -> Optional[Path]:
        relative = name.replace("\\", "/").lstrip("/")
        for folder in (model_dir, model_dir / "Exp3", model_dir / "Animation",
                       model_dir / "expressions", model_dir / "motions"):
            candidate = folder / relative
            if candidate.is_file() and _inside(model_dir, candidate):
                return candidate
        return indexed.get(Path(relative).name.lower())

    return resolve


def _merge_vtube(model_path: Path, data: dict) -> tuple[int, int]:
    vtube_path = _vtube_file(model_path)
    if vtube_path is None:
        return 0, 0
    vtube = _read_json(vtube_path)
    refs = data.setdefault("FileReferences", {})
    expressions = refs.setdefault("Expressions", [])
    motions = refs.setdefault("Motions", {})
    resolve = _resource_resolver(model_path.parent)
    expression_files = {
        item.get("File", "").replace("\\", "/").lower()
        for item in expressions if isinstance(item, dict)
    }
    motion_files = {
        item.get("File", "").replace("\\", "/").lower()
        for group in motions.values() if isinstance(group, list)
        for item in group if isinstance(item, dict)
    }
    added_expressions = 0
    added_motions = 0

    def relative(path: Path) -> str:
        return path.relative_to(model_path.parent).as_posix()

    def add_expression(name: str, filename: str) -> None:
        nonlocal added_expressions
        path = resolve(filename)
        if path is None:
            return
        rel = relative(path)
        if rel.lower() in expression_files:
            return
        expressions.append({"Name": name or path.stem, "File": rel})
        expression_files.add(rel.lower())
        added_expressions += 1

    def add_motion(group: str, filename: str, idle: bool = False) -> None:
        nonlocal added_motions
        path = resolve(filename)
        if path is None:
            return
        if not idle:
            motion_data = _read_json(path)
            meta = motion_data.setdefault("Meta", {})
            if meta.get("Loop"):
                meta["Loop"] = False
                _write_json(path, motion_data)
        rel = relative(path)
        if rel.lower() in motion_files:
            return
        item = {"File": rel}
        if idle:
            item.update({"FadeInTime": 1.0, "FadeOutTime": 1.0})
        motions.setdefault(group, []).append(item)
        motion_files.add(rel.lower())
        added_motions += 1

    vtube_refs = vtube.get("FileReferences") or {}
    if vtube_refs.get("IdleAnimation"):
        add_motion("Idle", vtube_refs["IdleAnimation"], idle=True)
    if vtube_refs.get("IdleAnimationWhenTrackingLost"):
        add_motion("TrackingLost", vtube_refs["IdleAnimationWhenTrackingLost"], idle=True)

    for hotkey in vtube.get("Hotkeys") or []:
        if not isinstance(hotkey, dict):
            continue
        filename = hotkey.get("File") or ""
        name = hotkey.get("Name") or Path(filename).stem
        action = hotkey.get("Action")
        if action == "ToggleExpression" and filename:
            add_expression(name, filename)
        elif action == "TriggerAnimation" and filename:
            add_motion(name, filename)

    return added_expressions, added_motions


def _resize_textures(model_path: Path, data: dict) -> int:
    refs = data.get("FileReferences") or {}
    textures = refs.get("Textures") or []
    resized = 0
    for index, filename in enumerate(textures):
        texture = model_path.parent / filename
        if not texture.is_file() or not _inside(model_path.parent, texture):
            continue
        optimized = texture.with_name(f"{texture.stem}.max{MAX_TEXTURE_SIZE}{texture.suffix}")
        tmp = optimized.with_name(optimized.name + ".tmp")
        try:
            with Image.open(texture) as image:
                if max(image.size) <= MAX_TEXTURE_SIZE:
                    continue
                scale = MAX_TEXTURE_SIZE / max(image.size)
                size = (round(image.width * scale), round(image.height * scale))
                resampling = getattr(Image, "Resampling", Image)
                resized_image = image.resize(size, resampling.LANCZOS)
                resized_image.save(tmp, format="PNG", optimize=True)
            tmp.replace(optimized)
            textures[index] = optimized.relative_to(model_path.parent).as_posix()
            resized += 1
        except Exception as exc:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            print(f"[live2d] texture resize skipped: {type(exc).__name__}")
    return resized


def normalize_live2d_model(model_path: Path) -> dict[str, int]:
    """Downscale oversized textures and merge VTS-only motions/expressions."""
    empty = {"textures_resized": 0, "expressions_added": 0, "motions_added": 0}
    try:
        data = _read_json(model_path)
        expressions, motions = _merge_vtube(model_path, data)
        textures = _resize_textures(model_path, data)
        if expressions or motions or textures:
            _write_json(model_path, data)
        return {
            "textures_resized": textures,
            "expressions_added": expressions,
            "motions_added": motions,
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[live2d] normalization skipped: {type(exc).__name__}")
        return empty

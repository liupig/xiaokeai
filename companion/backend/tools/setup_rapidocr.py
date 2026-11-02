"""Provision pinned, checksum-verified CPU OCR models into project data."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import importlib.util

import yaml

ROOT = Path(__file__).resolve().parents[1] / "data/ocr"
KEYS = {"det": "ch_PP-OCRv5_det_mobile", "cls": "ch_PP-LCNet_x0_25_textline_ori_cls_mobile",
        "rec": "ch_PP-OCRv5_rec_mobile", "ko": "korean_PP-OCRv5_rec_mobile"}


def main():
    config_path = ROOT / "runtime/rapidocr/default_models.yaml"
    if not config_path.is_file():
        spec = importlib.util.find_spec("rapidocr")
        if spec is None or not spec.origin:
            raise RuntimeError("Install rapidocr==3.10.0 before provisioning models")
        config_path = Path(spec.origin).with_name("default_models.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["onnxruntime"]["PP-OCRv5"]
    folder = ROOT / "models"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for role, key in KEYS.items():
        source = config["rec" if role == "ko" else role][key]
        target = folder / (key + ".onnx")
        checksum = source["SHA256"].lower()
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            temporary = target.with_suffix(".part")
            for attempt in range(3):
                with urllib.request.urlopen(source["model_dir"], timeout=60) as response, temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() == checksum:
                    break
            else:
                raise RuntimeError("Model checksum mismatch: " + key)
            os.replace(temporary, target)
        manifest[role] = {"file": target.name, "bytes": target.stat().st_size, "sha256": checksum, "url": source["model_dir"]}
        print(json.dumps({"model": key, "bytes": target.stat().st_size}), flush=True)
    (ROOT / "models.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

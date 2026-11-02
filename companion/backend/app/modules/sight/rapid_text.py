"""Resident CPU OCR. Share detection across Chinese/English/Japanese/Korean reads."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import threading

_lock = threading.Lock()
_engine = None
_korean = None


def home() -> Path:
    explicit = os.environ.get("XIAOKE_OCR_HOME")
    if explicit:
        return Path(explicit)
    packed = os.environ.get("COMPANION_ROOT")
    return Path(packed) / "data/ocr" if packed else Path(__file__).resolve().parents[3] / "data/ocr"


def _params(language="ch", recognition_only=False):
    from rapidocr import OCRVersion, ModelType
    folder = home() / "models"
    params = {"Global.log_level": "error", "Global.text_score": 0.0,
              "Global.use_cls": False, "Global.use_det": not recognition_only,
              "Global.model_root_dir": str(folder),
              "EngineConfig.onnxruntime.intra_op_num_threads": 2,
              "EngineConfig.onnxruntime.inter_op_num_threads": 1,
              "EngineConfig.onnxruntime.use_cuda": False,
              "EngineConfig.onnxruntime.use_dml": False,
              "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": ModelType.MOBILE, "Det.lang_type": "ch",
              "Det.model_path": str(folder / "ch_PP-OCRv5_det_mobile.onnx"),
              "Det.limit_side_len": 1280, "Det.limit_type": "max",
              "Cls.model_path": str(folder / "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"),
              "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE, "Rec.lang_type": language,
              "Rec.model_path": str(folder / ("korean_PP-OCRv5_rec_mobile.onnx" if language == "korean" else "ch_PP-OCRv5_rec_mobile.onnx"))}
    return params


def _load():
    global _engine, _korean
    if _engine is not None:
        return
    folder = home()
    runtime = folder / "runtime"
    if runtime.is_dir() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))
    if not (folder / "models.json").is_file():
        raise FileNotFoundError("RapidOCR models are not provisioned")
    from rapidocr import RapidOCR
    primary = RapidOCR(params=_params())
    korean = RapidOCR(params=_params("korean", True))
    _engine, _korean = primary, korean


def read(image) -> list[dict]:
    import numpy as np
    import cv2
    with _lock:
        _load()
        bgr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        result = _engine(bgr)
        if result.boxes is None or result.txts is None or not len(result.boxes):
            return []
        # A second recognizer reuses detected boxes instead of detecting twice.
        crops, candidates = [], []
        for index, box in enumerate(result.boxes):
            if float(result.scores[index]) >= .92 and not re.search(r"[\uac00-\ud7af]", result.txts[index]):
                continue
            left, top = np.floor(np.min(box, axis=0)).astype(int)
            right, bottom = np.ceil(np.max(box, axis=0)).astype(int)
            crop = bgr[max(0, top):min(bgr.shape[0], bottom+1), max(0, left):min(bgr.shape[1], right+1)].copy()
            if crop.size:
                crops.append(crop)
                candidates.append(index)
        alternatives = {}
        if crops:
            ko = _korean.recognize_txt(crops)
            if ko.txts:
                alternatives = {index: (text, float(score)) for index, text, score in zip(candidates, ko.txts, ko.scores)}
        rows = []
        for index, (box, text, confidence) in enumerate(zip(result.boxes, result.txts, result.scores)):
            language = "zh-en-ja"
            if index in alternatives:
                candidate, score = alternatives[index]
                if re.search(r"[\uac00-\ud7af]", candidate) and score >= .85 and score >= float(confidence)-.02:
                    text, confidence, language = candidate, score, "ko"
            if float(confidence) < .5 or not str(text).strip():
                continue
            left, top = np.min(box, axis=0)
            right, bottom = np.max(box, axis=0)
            rows.append({"text": str(text), "confidence": round(float(confidence), 4), "language": language,
                         "engine": "rapidocr", "words": [{"text": str(text), "x": float(left), "y": float(top),
                         "width": float(right-left), "height": float(bottom-top)}]})
        return rows

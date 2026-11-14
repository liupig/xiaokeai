from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SELECTED = {
    "Breathing_Idle": ("呼吸待机", "idle"),
    "Happy_Idle": ("开心待机", "idle"),
    "Sad_Idle": ("低落待机", "idle"),
    "Sitting_Idle_3": ("坐姿呼吸待机", "idle"),
    "Standing_Idle_02": ("站立张望待机", "idle"),
    "Clapping": ("站立鼓掌", "interact"),
    "Standing_Greeting": ("站立问好", "greet"),
    "Thankful": ("感谢", "interact"),
    "Thinking": ("思考", "interact"),
    "Talking_2": ["交谈手势", "interact"],
    "Agreeing_2": ("赞同点头", "interact"),
    "Shaking_Head_No": ("摇头否定", "interact"),
    "Happy_Hand_Gesture": ("开心招手", "greet"),
    "Laughing": ["开心大笑", "interact"],
    "Yawn": ["打哈欠", "idle"],
    "Blow_A_Kiss": ["飞吻", "interact"],
    "Look_Around_2": ["好奇张望", "idle"],
    "Listening_To_Music": ["听音乐", "idle"],
    "Macarena_Dance": ["Macarena", "dance"],
    "Gangnam_Style": ["江南 Style", "dance"],
    "Chicken_Dance": ["小鸡舞", "dance"],
    "Salsa_Dancing_5": ["Salsa 双人步", "dance"],
}
assert len(SELECTED) == 22


def read_action_sheet(path: Path):
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {node.attrib["Id"]: node.attrib["Target"] for node in rels_root}
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(node.itertext()) for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        sheet = next(node for node in workbook.find("m:sheets", ns) if node.attrib["name"] == "动作清单")
        target = "xl/" + rels[sheet.attrib[f"{{{ns['r']}}}id"]]
        root = ET.fromstring(archive.read(target))
        result = {}
        for row in root.findall(".//m:sheetData/m:row", ns):
            values = {}
            for cell in row.findall("m:c", ns):
                value = cell.find("m:v", ns)
                text = "" if value is None else value.text
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values[cell.attrib["r"][0]] = text
            if values.get("B"):
                result[values["B"]] = values
        return result


def download(item, input_dir):
    name, row = item
    url = row["H"].replace("/animation/", "/animation_motion/")
    destination = input_dir / f"{name}.fbx"
    if not destination.is_file():
        with urllib.request.urlopen(url, timeout=90) as response, destination.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
    return name, destination.stat().st_size


def main():
    parser = argparse.ArgumentParser(description="按 Excel 精选清单构建 xiaokeai Mixamo VMD 动作包")
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--model", type=Path, default=ROOT / "assets/models/qingxiao/model.pmx")
    parser.add_argument("--input", type=Path, default=ROOT / "../_dl/mixamo-pack-selection")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/motions/xiaokeai-mixamo")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--offline", action="store_true", help="只使用本地仓库，不下载")
    args = parser.parse_args()
    rows = read_action_sheet(args.xlsx)
    missing = sorted(set(SELECTED) - set(rows))
    if missing:
        raise ValueError(f"Excel 中找不到：{missing}")
    args.input.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.offline:
        missing_files = [name for name in SELECTED if not (args.input / f"{name}.fbx").is_file()]
        if missing_files:
            raise FileNotFoundError(f"本地仓库缺少：{missing_files}")
        print(f"已使用本地仓库的 {len(SELECTED)} 个 FBX", flush=True)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            downloaded = list(pool.map(lambda item: download(item, args.input), ((name, rows[name]) for name in SELECTED)))
        print(f"已准备 {len(downloaded)} 个 FBX", flush=True)
    if not args.skip_convert:
        selected_files = [str(args.input / f"{name}.fbx") for name in SELECTED]
        subprocess.run([
            sys.executable, str(ROOT / "motionlab/blender_convert.py"),
            "--model", str(args.model), "--output", str(args.output),
            *selected_files, "--fail-fast",
        ], cwd=ROOT, check=True)
    manifest = []
    for name, (label, category) in SELECTED.items():
        vmd = args.output / f"{name}.vmd"
        if not vmd.is_file():
            raise FileNotFoundError(vmd)
        manifest.append({
            "file": vmd.name, "label": label, "category": category,
            "seconds": float(rows[name]["D"]), "description": rows[name].get("E", ""),
            "source": rows[name]["H"].replace("/animation/", "/animation_motion/"),
        })
    (args.output / "manifest.json").write_text(
        json.dumps({"pack": "xiaokeai-mixamo", "version": 1, "motions": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"动作包完成：{args.output}（{len(manifest)} 个 VMD）", flush=True)


if __name__ == "__main__":
    main()

"""Read-only audit of one final PMX and its texture dependencies in a ZIP. Python 3.8+."""
import argparse
import json
import posixpath
import re
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0

    def take(self, size):
        end = self.pos + size
        if size < 0 or end > len(self.data):
            raise ValueError("Invalid PMX length or truncated file")
        part = self.data[self.pos:end]
        self.pos = end
        return part

    def byte(self):
        return self.take(1)[0]

    def count(self):
        value, = struct.unpack("<i", self.take(4))
        if value < 0:
            raise ValueError("Negative PMX count")
        return value

    def string(self):
        return self.take(self.count()).tobytes().decode(self.encoding)


def read_materials(data):
    r = Reader(data)
    if r.take(4) != b"PMX ":
        raise ValueError("Invalid PMX signature")
    version, = struct.unpack("<f", r.take(4))
    params = r.take(r.byte())
    if round(version, 2) not in (2.0,2.1) or len(params) < 8:
        raise ValueError("Expected a PMX 2.0 or 2.1 header")
    charset, extra_uv, vertex_index, texture_index, _, bone_index, _, _ = params[:8]
    if charset > 1 or extra_uv > 4 or any(n not in (1,2,4) for n in params[2:8]):
        raise ValueError("Unsupported PMX encoding or index dimensions")
    r.encoding = ("utf-16-le","utf-8")[charset]
    name, _, _, _ = [r.string() for _ in range(4)]
    sizes = (bone_index, 2*bone_index+4, 4*bone_index+16, 2*bone_index+40, 4*bone_index+16)
    for _ in range(r.count()):
        r.take(32+extra_uv*16)
        weight = r.byte()
        if weight >= len(sizes):
            raise ValueError("Unknown PMX vertex weight type")
        r.take(sizes[weight]+4)
    index_count = r.count()
    r.take(index_count*vertex_index)
    textures = [r.string() for _ in range(r.count())]
    active = []
    total = 0
    for _ in range(r.count()):
        slot = r.string()
        r.string()
        r.take(65)  # diffuse, specular, exponent, ambient, flags, edge RGBA and width
        def texture_ref():
            idx = int.from_bytes(r.take(texture_index),"little",signed=True)
            if idx < -1 or idx >= len(textures):
                raise ValueError(f"Out-of-range texture index in {slot}")
            return textures[idx] if idx >= 0 else None
        base, sphere = texture_ref(), texture_ref()
        r.byte()
        shared = r.byte()
        if shared not in (0,1):
            raise ValueError(f"Invalid toon flag in {slot}")
        toon = None
        if shared:
            r.byte()
        else:
            toon = texture_ref()
        r.string()
        count = r.count()
        if count % 3:
            raise ValueError(f"Incomplete triangle in {slot}")
        total += count
        if count:
            active.append(dict(slot=slot,triangles=count//3,textures=[t for t in (base,sphere,toon) if t]))
    if total != index_count:
        raise ValueError("Material index counts do not match mesh")
    return name,textures,active


def normalized(path):
    path = path.replace("\\","/")
    result = posixpath.normpath(path)
    if path.startswith("/") or re.match(r"^[A-Za-z]:",path) or result in (".","..") or result.startswith("../"):
        raise ValueError(f"Path outside the archive: {path}")
    return result


def audit(path):
    with zipfile.ZipFile(path) as z:
        members = [f for f in z.infolist() if not f.is_dir()]
        names = [normalized(f.filename) for f in members]
        if any(count>1 for count in Counter(n.casefold() for n in names).values()):
            raise ValueError("Duplicate or case-colliding archive paths")
        files = dict(zip(names,members))
        models = [p for p in files if p.lower().endswith(".pmx")]
        if len(models)!=1:
            raise ValueError(f"Expected one final PMX, found {len(models)}")
        corrupt = z.testzip()
        if corrupt:
            raise ValueError(f"CRC failure in {corrupt}")
        pmx, = models
        name,textures,active = read_materials(z.read(files[pmx]))
        folder = posixpath.dirname(pmx)
        def relative(p):
            if not isinstance(p,str) or not p or re.match(r"^([/\\]|[A-Za-z]:)",p):
                raise ValueError(f"Invalid relative resource: {p!r}")
            return normalized(posixpath.join(folder,p))
        dependencies = {relative(t) for t in textures if t}
        sidecar = relative("xiaokeai-pbr.json")
        active_names = {row["slot"] for row in active}
        mapped = {}
        if sidecar in files:
            profile = json.loads(z.read(files[sidecar]))
            if not isinstance(profile,dict) or profile.get("version")!=1:
                raise ValueError("Unsupported xiaokeai-pbr.json")
            for recipe in profile["finishes"]:
                for slot in active_names.intersection(recipe["materials"]):
                    mapped[slot] = "physical"
                    if recipe["map"]:
                        dependencies.add(relative("textures/yuexiao-"+recipe["map"]+"-finish.png"))
            for slot,mask in profile.get("skinZones",{"Face_":"skin-zones"}).items():
                if slot in active_names:
                    mapped[slot] = "skin"
                    dependencies.add(relative("textures/yuexiao-"+mask+"-finish.png"))
        for row in active:
            row["finish"] = mapped.get(row["slot"],"native")
        return dict(model=name,pmx=pmx,members=len(files),packed_bytes=path.stat().st_size,
                    has_xiaokeai_pbr=sidecar in files,coverage=dict(Counter(row["finish"] for row in active)),
                    missing=sorted(dependencies-files.keys()),materials=active,
                    largest=[dict(path=f.filename,packed_bytes=f.compress_size)
                             for f in sorted(members,key=lambda f:f.compress_size,reverse=True)[:5]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.archive)
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,RuntimeError) as error:
        print(f"Audit failed: {error}",file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if report["missing"] else 0


if __name__=="__main__":
    sys.exit(main())

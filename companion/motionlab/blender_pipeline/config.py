"""Mixamo → MMD 骨骼映射。源名称不带 mixamorig 前缀和冒号。"""

BONE_MAP = {
    "Hips": "センター",
    "Neck": "首",
    "Head": "頭",
}

for side, jp in (("Left", "左"), ("Right", "右")):
    BONE_MAP.update({
        f"{side}Shoulder": f"{jp}肩",
        f"{side}Arm": f"{jp}腕",
        f"{side}ForeArm": f"{jp}ひじ",
        f"{side}Hand": f"{jp}手首",
        f"{side}UpLeg": f"{jp}足",
        f"{side}Leg": f"{jp}ひざ",
        f"{side}Foot": f"{jp}足首",
        f"{side}ToeBase": f"{jp}つま先",
    })

FINGERS = (
    ("Thumb", "親指"),
    ("Index", "人指"),
    ("Middle", "中指"),
    ("Ring", "薬指"),
    ("Pinky", "小指"),
)
for side, jp in (("Left", "左"), ("Right", "右")):
    for finger, mmd in FINGERS:
        for index in range(1, 4):
            joint = index - 1 if finger == "Thumb" else index
            BONE_MAP[f"{side}Hand{finger}{index}"] = f"{jp}{mmd}{'０１２３'[joint]}"

# 源子骨、目标子骨。除了确定骨骼方向，还用第二参考轴约束 roll。
REST_CHILDREN = {
    "Hips": ("Spine", "上半身"),
    "Spine": ("Spine1", "上半身"),
    "Spine1": ("Spine2", "上半身2"),
    "Spine2": ("Neck", "首"),
    "Neck": ("Head", "頭"),
}
for side, jp in (("Left", "左"), ("Right", "右")):
    REST_CHILDREN.update({
        f"{side}Shoulder": (f"{side}Arm", f"{jp}腕"),
        f"{side}Arm": (f"{side}ForeArm", f"{jp}ひじ"),
        f"{side}ForeArm": (f"{side}Hand", f"{jp}手首"),
        f"{side}Hand": (f"{side}HandMiddle1", f"{jp}中指１"),
        f"{side}UpLeg": (f"{side}Leg", f"{jp}ひざ"),
        f"{side}Leg": (f"{side}Foot", f"{jp}足首"),
        f"{side}Foot": (f"{side}ToeBase", f"{jp}つま先"),
    })
    for finger, mmd in FINGERS:
        for index in range(1, 3):
            joint = index - 1 if finger == "Thumb" else index
            next_joint = joint + 1
            REST_CHILDREN[f"{side}Hand{finger}{index}"] = (
                f"{side}Hand{finger}{index + 1}", f"{jp}{mmd}{'０１２３'[next_joint]}",
            )


def mixamo_name(blender_name: str) -> str:
    if not blender_name.startswith("mixamorig"):
        return ""
    name = blender_name[len("mixamorig"):]
    return name[1:] if name.startswith(":") else name

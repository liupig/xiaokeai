from motionlab.blender_pipeline.config import BONE_MAP, mixamo_name


def test_mixamo_names_accept_standard_namespace():
    assert mixamo_name("mixamorig:Hips") == "Hips"
    assert mixamo_name("mixamorigHips") == "Hips"
    assert mixamo_name("Armature") == ""


def test_map_contains_full_fingers_and_humanoid_core():
    assert BONE_MAP["Hips"] == "センター"
    assert BONE_MAP["RightArm"] == "右腕"
    assert BONE_MAP["LeftLeg"] == "左ひざ"
    assert BONE_MAP["RightHandMiddle3"] == "右中指３"
    assert BONE_MAP["LeftHandThumb3"] == "左親指２"
    assert len(BONE_MAP) == 49
    assert len({*BONE_MAP, "Spine1", "Spine2"}) == 51

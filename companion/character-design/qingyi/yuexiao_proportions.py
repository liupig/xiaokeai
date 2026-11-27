"""Fit the two-view Yuexiao silhouette in the PMX bind pose."""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.spatial.transform import Rotation


def lengthen_legs(model):
    bones = {b.name: b for b in model.bones}
    ankle, knee, hip = [bones[name].location[1] for name in ('左足首', '左ひざ', '左足')]
    shin_rise = .15 * (knee - ankle)
    rise = shin_rise + .07 * (hip - knee)
    # The extra length fades into the ankle and hip. The sole and the
    # torso retain their shapes, and the knee gets a continuous surface normal.
    curve = PchipInterpolator([ankle-1, ankle, knee, hip, hip+1],
                              [0, 0, shin_rise, rise, rise])

    def shift(y):
        return curve(np.clip(y, ankle, hip))

    def move(position, dy):
        x, y, z = position
        return (x, y + float(dy), z)

    # A skirt leaf or a long curl can reach the knee in the bind pose.
    # Fit the skin and its sandal details by height; translate the ensemble
    # from the pelvis so its cut and its drape remain consistent.
    leg_skin = np.zeros(len(model.vertices), dtype=bool)
    first = 0
    for mat in model.materials:
        last = first + mat.vertex_count // 3
        if last > first and (mat.name.startswith('Moon_Sandal') or mat.name in ('Down_Skin', 'Down_Metal', 'Down_Jewel', 'Down_Nail')):
            leg_skin[np.asarray(model.faces[first:last]).ravel()] = True
        first = last
    heights = np.array([vertex.co[1] for vertex in model.vertices])
    deltas = np.full(len(heights), rise)
    deltas[leg_skin] = shift(heights[leg_skin])
    slopes = 1 + curve.derivative()(np.clip(heights, ankle, hip))
    for i, vertex in enumerate(model.vertices):
        vertex.co = move(vertex.co, deltas[i])
        if leg_skin[i] and ankle < heights[i] < hip:
            normal = np.array(vertex.normal, dtype=float)
            normal[1] /= slopes[i]
            vertex.normal = normal / max(np.linalg.norm(normal), 1.e-12)
        if vertex.weight.type == vertex.weight.SDEF:
            weight = vertex.weight.weights
            for field in ('c', 'r0', 'r1'):
                point = getattr(weight, field)
                setattr(weight, field, move(point, shift(point[1]) if leg_skin[i] else rise))

    for morph in model.morphs:
        if morph.type_index() == 1:
            for offset in morph.offsets:
                i = offset.index
                if leg_skin[i]:
                    offset.offset = move(offset.offset, shift(heights[i] + offset.offset[1]) - deltas[i])

    def on_leg(i):
        while i is not None and i >= 0:
            bone = model.bones[i]
            if bone.name.startswith(('腰キャンセル', 'Leg_')) or bone.name.endswith('足IK親'):
                return True
            i = bone.parent
        return False

    leg_bones = {i for i in range(len(model.bones)) if on_leg(i)}
    for i, bone in enumerate(model.bones):
        y = bone.location[1]
        if bone.name in ('全ての親', '操作中心'):
            continue
        dy = shift(y) if i in leg_bones else rise
        if i in leg_bones and not isinstance(bone.displayConnection, int):
            tail = bone.displayConnection
            bone.displayConnection = move(tail, shift(y + tail[1]) - dy)
        bone.location = move(bone.location, dy)

    leg_rigids = {i for i, body in enumerate(model.rigids) if body.bone in leg_bones}
    for i, body in enumerate(model.rigids):
        y = body.location[1]
        if i in leg_rigids and body.type == body.TYPE_CAPSULE and ankle < y < hip:
            # Fit both ends of the thigh/calf collision cylinder. Keep its
            # radius and roll, and turn its axis to follow the refitted limb.
            orient = Rotation.from_euler('XYZ', body.rotation)
            axis = orient.apply([0., 1., 0.])
            half = axis * body.size[1] / 2
            ends = np.asarray(body.location) + np.array([-half, half])
            ends[:, 1] += shift(ends[:, 1])
            line = ends[1] - ends[0]
            length = np.linalg.norm(line)
            direction = line / length
            turn = Rotation.from_quat([*np.cross(axis, direction), 1 + np.dot(axis, direction)])
            body.rotation = (turn * orient).as_euler('XYZ')
            body.size = (body.size[0], length, body.size[2])
            body.location = ends.mean(axis=0)
        else:
            body.location = move(body.location, shift(y) if i in leg_rigids else rise)
    for joint in model.joints:
        dy = shift(joint.location[1]) if joint.dest_rigid in leg_rigids else rise
        joint.location = move(joint.location, dy)

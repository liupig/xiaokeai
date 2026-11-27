"""Yuexiao's jaw, eyelids and painted eye materials on the Xinyuehu head."""
import numpy as np
from PIL import Image, ImageDraw

from build_lanxu import DESIGN, OUT, PMX, TEX


def bind_eye_art(tailor):
    # The iris mesh reads an elliptical UV chart. Its auxiliary eye shell
    # shares this atlas and reads the three flat swatches in the corners.
    size = 1024
    painting = Image.open(DESIGN/'yuexiao-iris-paint.png').convert('RGB')
    atlas = Image.new('RGB', (size, size), painting.getpixel((0, 0)))
    chart = painting.resize((872, 978), Image.LANCZOS)
    atlas.paste(chart, ((size-chart.width)//2, (size-chart.height)//2))
    draw = ImageDraw.Draw(atlas)
    for left, top, right, bottom, rgb in [
        (.84, .032, .985, .119, (174, 157, 145)),
        (.04, .872, .226, .965, (219, 211, 206)),
        (.774, .872, .96, .965, (219, 211, 206)),
    ]:
        draw.rectangle(tuple(round(z*size) for z in (left, top, right, bottom)), fill=rgb)
    atlas.save(TEX/'yuexiao-painted-iris.png')

    # Keep the corneal reflections on the original moving highlight layer.
    # The UVs on both eyes have the same orientation in character space.
    y, x = (np.indices((size, size), dtype=np.float32) + .5)/size
    dx, dy = x-.378, y-.440
    key = ((dx-.25*dy)/.064)**2 + (dy/.054)**2
    bounce = ((x-.650)/.023)**2 + ((y-.600)/.020)**2
    alpha = np.maximum(.92*smooth((1.12-key)/.38), .80*smooth((1.14-bounce)/.46))
    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = (255, 249, 238)
    rgba[bounce < 1.14, :3] = (255, 232, 191)
    rgba[:, :, 3] = np.rint(255*alpha)
    Image.fromarray(rgba).save(TEX/'yuexiao-corneal-light.png')
    for mat in tailor.m.materials:
        if mat.name in ('Eye_', 'Eye_+'):
            mat.texture = tailor.tex('yuexiao-painted-iris.png')
        elif mat.name == 'Eye_Hi':
            mat.texture = tailor.tex('yuexiao-corneal-light.png')


def without_undereye_mark(model, faces):
    # This isolated 16-triangle decal uses a red swatch in the facial atlas.
    # Drop just its faces, retaining the underlying cheek and PMX morph indices.
    patch = {i for i in np.unique(faces)
             if .96 < model.vertices[i].uv[0] < .995 and .265 < model.vertices[i].uv[1] < .298}
    kept = [tri for tri in faces if not all(i in patch for i in tri)]
    if len(patch) != 17 or len(faces)-len(kept) != 16 or any(i in patch for tri in kept for i in tri):
        raise ValueError('The under-eye decal must be an isolated UV island')
    return kept


def face_groups(model):
    groups = {}
    first = 0
    for mat in model.materials:
        end = first + mat.vertex_count // 3
        if mat.name.startswith(('Face', 'Eye_')):
            groups[mat.name] = np.asarray(model.faces[first:end])
        first = end
    return groups


def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3 - 2*t)


def soften_jaw(points):
    x, y, z = points.T
    # Compact support keeps the lips, nose, eyes, chin tip and neck seam
    # pinned. The outer lower jaw gains at most 1.52 mm per side at 0.08 m/unit.
    height = np.clip(1 - ((y - 18.98)/.40)**2, 0, 1)**2
    outer = smooth((np.abs(x) - .25)/.22)
    front = smooth((.22 - z)/.20)
    fitted = points.copy()
    fitted[:, 0] += .019 * np.sign(x) * height * outer * front
    return fitted


def shape_eyelids(points):
    x, y, z = points.T
    side = np.abs(x)
    # Work in the orbit. Both corners and the brow have their own falloffs.
    mask = smooth((side-.14)/.12) * smooth((.91-side)/.08)
    mask *= smooth((y-19.36)/.10) * smooth((19.795-y)/.10)
    mask *= smooth((.00-z)/.055)
    arch = np.clip(1-((side-.43)/.285)**2, 0, 1)**2
    upper = smooth((y-19.532)/.078)
    lower = smooth((19.535-y)/.060)
    corner = np.clip(1-((side-.615)/.19)**2, 0, 1)**2
    wing = .042*smooth((side-.58)/.24)*mask
    fitted = points.copy()
    fitted[:, 0] -= np.sign(x)*wing
    fitted[:, 1] += mask*(arch*(.019*upper-.005*lower) + .010*corner)
    # The tapered outer lashes follow the depth of the temple in three-quarter view.
    fitted[:, 2] -= .67*wing
    return fitted


def fit_surface(model, ids, warp):
    rest = np.array([model.vertices[i].co for i in ids])
    fitted = warp(rest)
    active = np.flatnonzero(np.any(fitted != rest, axis=1))
    points = rest[active]
    step = .0001
    jac = np.stack([(warp(points+d) - warp(points-d))/(2*step)
                    for d in np.eye(3)*step], axis=-1)
    normals = np.array([model.vertices[i].normal for i in ids[active]])
    normals = np.linalg.solve(jac.transpose(0, 2, 1), normals[..., None])[..., 0]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    for vertex, position, normal in zip(ids[active], fitted[active], normals):
        model.vertices[vertex].co = tuple(position)
        model.vertices[vertex].normal = tuple(normal)
    return rest, fitted


def fit_portrait(model):
    native = PMX['load'](str(OUT.parent / 'xinyuehu/model.pmx'))
    original, current = face_groups(native), face_groups(model)
    if original.keys() != current.keys() or any(
        not np.array_equal(tris, current[name]) for name, tris in original.items()
    ):
        raise ValueError('The native head and the delivery rig must share face topology')

    ids = set(np.concatenate(list(original.values())).ravel().tolist())
    for index in ids:
        dst, src = model.vertices[index], native.vertices[index]
        dst.co, dst.normal = src.co, src.normal

    # The earlier base was sculpted from these same indices. Restore native
    # expression deltas too, retaining the wardrobe and all body expressions.
    native_morphs = {m.name: m for m in native.morphs if m.type_index() == 1}
    for morph in model.morphs:
        if morph.type_index() != 1 or morph.name not in native_morphs:
            continue
        facial = [o for o in native_morphs[morph.name].offsets if o.index in ids]
        morph.offsets = [o for o in morph.offsets if o.index not in ids] + facial

    fit_surface(model, np.unique(original['Face_']), soften_jaw)
    lid_groups = ('Face_', 'Face_Eyelash', 'Face_Eyewhite', 'Eye_+')
    eyelids = np.unique(np.concatenate([original[group] for group in lid_groups]))
    rest, fitted = fit_surface(model, eyelids, shape_eyelids)
    lookup = {index: k for k, index in enumerate(eyelids)}
    # Fit the closed and smiling lids in the same space as the open lids.
    # This also keeps the sclera and its moving mask behind the lash line.
    for morph in model.morphs:
        if morph.type_index() != 1:
            continue
        offsets = [o for o in morph.offsets if o.index in lookup]
        if offsets:
            rows = [lookup[o.index] for o in offsets]
            posed = rest[rows] + [o.offset for o in offsets]
            delta = (shape_eyelids(posed)-posed) - (fitted[rows]-rest[rows])
            for offset, correction in zip(offsets, delta):
                if np.any(correction):
                    offset.offset = tuple(offset.offset + correction)

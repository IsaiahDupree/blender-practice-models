"""Generate three real practice models and studio previews in Blender 4.4.

Run with Blender, not CPython:
    blender --background --factory-startup --python build_practice_models.py -- OUTPUT_DIR
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


def output_root() -> Path:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("expected exactly one output directory after --")
    root = Path(args[0]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.35,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission_strength:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def add_bevel(obj: bpy.types.Object, width: float, segments: int = 3) -> None:
    modifier = obj.modifiers.new(name="Edge softening", type="BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"


def add_cube(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.08,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        add_bevel(obj, bevel)
    obj.data.materials.append(mat)
    return obj


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_studio(
    *,
    camera_location: tuple[float, float, float],
    target: tuple[float, float, float],
    resolution: tuple[int, int] = (900, 900),
    floor_size: float = 24.0,
) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    world = scene.world or bpy.data.worlds.new("Practice Studio World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.012, 0.018, 0.035, 1.0)
    background.inputs["Strength"].default_value = 0.35

    floor_mat = material("Studio floor", (0.055, 0.07, 0.10, 1.0), roughness=0.28)
    bpy.ops.mesh.primitive_plane_add(size=floor_size, location=(0.0, 0.0, -0.015))
    floor = bpy.context.object
    floor.name = "Studio Floor"
    floor.data.materials.append(floor_mat)

    bpy.ops.object.light_add(type="AREA", location=(4.5, -4.5, 8.0))
    key = bpy.context.object
    key.name = "Key Light"
    key.data.energy = 1150
    key.data.shape = "DISK"
    key.data.size = 5.0
    key.data.color = (1.0, 0.83, 0.68)
    look_at(key, target)

    bpy.ops.object.light_add(type="AREA", location=(-5.0, -1.5, 4.5))
    fill = bpy.context.object
    fill.name = "Fill Light"
    fill.data.energy = 850
    fill.data.size = 5.0
    fill.data.color = (0.45, 0.68, 1.0)
    look_at(fill, target)

    bpy.ops.object.light_add(type="AREA", location=(2.0, 5.0, 7.0))
    rim = bpy.context.object
    rim.name = "Rim Light"
    rim.data.energy = 1300
    rim.data.size = 4.0
    rim.data.color = (0.42, 0.60, 1.0)
    look_at(rim, target)

    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.name = "Studio Camera"
    camera.data.lens = 56
    look_at(camera, target)
    scene.camera = camera


def create_gear() -> list[bpy.types.Object]:
    teeth = 24
    points = teeth * 4
    root_radius = 2.42
    tip_radius = 3.0
    bore_radius = 0.78
    thickness = 0.68
    vertices: list[tuple[float, float, float]] = []

    def radius_for(index: int) -> float:
        phase = index % 4
        return tip_radius if phase in (1, 2) else root_radius

    for z in (0.0, thickness):
        for index in range(points):
            angle = 2.0 * math.pi * index / points
            radius = radius_for(index)
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
    for z in (0.0, thickness):
        for index in range(points):
            angle = 2.0 * math.pi * index / points
            vertices.append((bore_radius * math.cos(angle), bore_radius * math.sin(angle), z))

    outer_bottom = 0
    outer_top = points
    inner_bottom = points * 2
    inner_top = points * 3
    faces: list[tuple[int, int, int, int]] = []
    for index in range(points):
        nxt = (index + 1) % points
        faces.extend(
            [
                (outer_bottom + index, outer_bottom + nxt, outer_top + nxt, outer_top + index),
                (inner_bottom + nxt, inner_bottom + index, inner_top + index, inner_top + nxt),
                (outer_top + index, outer_top + nxt, inner_top + nxt, inner_top + index),
                (outer_bottom + nxt, outer_bottom + index, inner_bottom + index, inner_bottom + nxt),
            ]
        )

    mesh = bpy.data.meshes.new("24-tooth gear mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    gear = bpy.data.objects.new("24-Tooth Practice Gear", mesh)
    bpy.context.collection.objects.link(gear)
    gear.data.materials.append(
        material("Gear cobalt", (0.035, 0.19, 0.62, 1.0), metallic=0.88, roughness=0.2)
    )
    add_bevel(gear, 0.055, 3)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.94,
        minor_radius=0.11,
        major_segments=64,
        minor_segments=12,
        location=(0.0, 0.0, thickness + 0.035),
    )
    collar = bpy.context.object
    collar.name = "Gear Bore Collar"
    collar.data.materials.append(
        material("Gear highlight", (0.10, 0.42, 0.95, 1.0), metallic=0.8, roughness=0.16)
    )
    return [gear, collar]


def create_phone_stand() -> list[bpy.types.Object]:
    teal = material("Stand teal", (0.015, 0.55, 0.53, 1.0), metallic=0.25, roughness=0.24)
    dark = material("Stand grip", (0.018, 0.025, 0.035, 1.0), metallic=0.05, roughness=0.5)
    objects = [
        add_cube("Weighted Base", (0.0, 0.0, 0.24), (4.8, 3.4, 0.48), teal, bevel=0.16),
        add_cube(
            "Angled Backrest",
            (0.0, 0.66, 2.28),
            (4.15, 0.42, 4.25),
            teal,
            rotation=(math.radians(-15.0), 0.0, 0.0),
            bevel=0.16,
        ),
        add_cube("Phone Shelf", (0.0, -0.48, 0.72), (4.1, 1.35, 0.28), teal, bevel=0.11),
        add_cube("Left Cable Lip", (-1.18, -1.10, 1.02), (1.72, 0.30, 0.72), teal, bevel=0.11),
        add_cube("Right Cable Lip", (1.18, -1.10, 1.02), (1.72, 0.30, 0.72), teal, bevel=0.11),
        add_cube("Left Grip Pad", (-1.15, -1.265, 1.15), (1.45, 0.055, 0.30), dark, bevel=0.025),
        add_cube("Right Grip Pad", (1.15, -1.265, 1.15), (1.45, 0.055, 0.30), dark, bevel=0.025),
        add_cube(
            "Back Grip",
            (0.0, 0.405, 2.22),
            (3.25, 0.055, 1.18),
            dark,
            rotation=(math.radians(-15.0), 0.0, 0.0),
            bevel=0.08,
        ),
    ]
    return objects


def fin_mesh(angle: float, mat: bpy.types.Material, index: int) -> bpy.types.Object:
    radial = Vector((math.cos(angle), math.sin(angle), 0.0))
    tangent = Vector((-math.sin(angle), math.cos(angle), 0.0))
    profile = ((1.05, 2.35), (2.30, 0.68), (1.05, 0.78))
    half_thickness = 0.13
    vertices = []
    for offset in (-half_thickness, half_thickness):
        for radius, z_value in profile:
            point = radial * radius + tangent * offset
            vertices.append((point.x, point.y, z_value))
    faces = [
        (0, 1, 2),
        (5, 4, 3),
        (0, 3, 4, 1),
        (1, 4, 5, 2),
        (2, 5, 3, 0),
    ]
    mesh = bpy.data.meshes.new(f"Rocket fin {index} mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    fin = bpy.data.objects.new(f"Rocket Fin {index}", mesh)
    bpy.context.collection.objects.link(fin)
    fin.data.materials.append(mat)
    add_bevel(fin, 0.055, 2)
    return fin


def create_rocket() -> list[bpy.types.Object]:
    ivory = material("Rocket ivory", (0.88, 0.92, 0.98, 1.0), metallic=0.12, roughness=0.22)
    coral = material("Rocket coral", (0.95, 0.095, 0.055, 1.0), metallic=0.25, roughness=0.2)
    dark = material("Rocket engine", (0.025, 0.035, 0.065, 1.0), metallic=0.86, roughness=0.18)
    glass = material("Rocket window", (0.015, 0.30, 0.70, 1.0), metallic=0.45, roughness=0.08, emission_strength=0.35)
    objects: list[bpy.types.Object] = []

    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.22, depth=3.65, location=(0.0, 0.0, 2.62))
    body = bpy.context.object
    body.name = "Low-Poly Rocket Body"
    body.data.materials.append(ivory)
    add_bevel(body, 0.08, 3)
    objects.append(body)

    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.22, radius2=0.0, depth=2.05, location=(0.0, 0.0, 5.47))
    nose = bpy.context.object
    nose.name = "Rocket Nose Cone"
    nose.data.materials.append(coral)
    add_bevel(nose, 0.045, 2)
    objects.append(nose)

    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.48, radius2=0.78, depth=0.78, location=(0.0, 0.0, 0.42))
    nozzle = bpy.context.object
    nozzle.name = "Engine Bell"
    nozzle.data.materials.append(dark)
    add_bevel(nozzle, 0.045, 2)
    objects.append(nozzle)

    for index, angle in enumerate((0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0), start=1):
        objects.append(fin_mesh(angle, coral, index))

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0.0, -1.16, 3.47), scale=(0.42, 0.12, 0.42))
    window = bpy.context.object
    window.name = "Observation Window"
    window.data.materials.append(glass)
    objects.append(window)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.45,
        minor_radius=0.085,
        major_segments=40,
        minor_segments=10,
        location=(0.0, -1.20, 3.47),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    window_rim = bpy.context.object
    window_rim.name = "Window Rim"
    window_rim.data.materials.append(dark)
    objects.append(window_rim)

    for z_value in (1.20, 4.02):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=1.22,
            minor_radius=0.075,
            major_segments=48,
            minor_segments=10,
            location=(0.0, 0.0, z_value),
        )
        stripe = bpy.context.object
        stripe.name = f"Rocket Accent Ring {z_value:.2f}"
        stripe.data.materials.append(coral)
        objects.append(stripe)

    return objects


def select_only(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_render = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_model(
    root: Path,
    name: str,
    objects: list[bpy.types.Object],
    *,
    camera_location: tuple[float, float, float],
    target: tuple[float, float, float],
) -> dict[str, object]:
    model_dir = root / name
    model_dir.mkdir(parents=True, exist_ok=True)
    setup_studio(camera_location=camera_location, target=target)

    preview = model_dir / f"{name}.png"
    bpy.context.scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)

    blend = model_dir / f"{name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False)

    select_only(objects)
    glb = model_dir / f"{name}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
    )
    stl = model_dir / f"{name}.stl"
    bpy.ops.wm.stl_export(
        filepath=str(stl),
        export_selected_objects=True,
        apply_modifiers=True,
        ascii_format=False,
    )

    files = [preview, blend, glb, stl]
    return {
        "name": name,
        "objects": len(objects),
        "artifacts": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        ],
    }


def group(objects: list[bpy.types.Object], location: tuple[float, float, float], scale: float, rotation: tuple[float, float, float]) -> None:
    empty = bpy.data.objects.new("Gallery Group", None)
    bpy.context.collection.objects.link(empty)
    for obj in objects:
        obj.parent = empty
    empty.location = location
    empty.scale = (scale, scale, scale)
    empty.rotation_euler = rotation


def add_label(text: str, x_value: float) -> None:
    bpy.ops.object.text_add(location=(x_value, -1.86, 0.42), rotation=(math.radians(90.0), 0.0, 0.0))
    label = bpy.context.object
    label.name = f"{text} Label"
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.align_y = "CENTER"
    label.data.size = 0.42
    label.data.extrude = 0.012
    label.data.bevel_depth = 0.006
    label.data.materials.append(material("Gallery label", (0.78, 0.88, 1.0, 1.0), roughness=0.25, emission_strength=0.22))


def render_gallery(root: Path) -> Path:
    clear_scene()
    gear = create_gear()
    group(gear, (-4.6, 0.0, 1.35), 0.72, (math.radians(67.0), 0.0, math.radians(-10.0)))
    stand = create_phone_stand()
    group(stand, (0.0, 0.0, 0.24), 0.68, (0.0, 0.0, 0.0))
    rocket = create_rocket()
    group(rocket, (4.6, 0.0, 0.12), 0.60, (0.0, 0.0, math.radians(-10.0)))

    pedestal_mat = material("Pedestal", (0.08, 0.105, 0.16, 1.0), metallic=0.3, roughness=0.23)
    for x_value, width in ((-4.6, 4.6), (0.0, 4.6), (4.6, 4.2)):
        add_cube(f"Pedestal {x_value}", (x_value, 0.0, 0.18), (width, 3.5, 0.36), pedestal_mat, bevel=0.14)
    add_label("24T GEAR", -4.6)
    add_label("PHONE STAND", 0.0)
    add_label("LOW-POLY ROCKET", 4.6)

    setup_studio(
        camera_location=(10.6, -18.8, 8.2),
        target=(0.0, 0.0, 2.1),
        resolution=(1600, 900),
        floor_size=34.0,
    )
    gallery = root / "practice-model-gallery.png"
    bpy.context.scene.render.filepath = str(gallery)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / "practice-model-gallery.blend"), check_existing=False)
    return gallery


def main() -> None:
    root = output_root()
    started = time.monotonic()
    receipt: dict[str, object] = {
        "status": "running",
        "blender_version": bpy.app.version_string,
        "models": [],
    }
    try:
        specs = [
            ("practice-gear", create_gear, (6.7, -8.3, 6.2), (0.0, 0.0, 0.28)),
            ("practice-phone-stand", create_phone_stand, (7.0, -9.4, 5.5), (0.0, 0.0, 1.65)),
            ("practice-low-poly-rocket", create_rocket, (7.5, -10.7, 6.8), (0.0, 0.0, 3.05)),
        ]
        for name, builder, camera_location, target in specs:
            clear_scene()
            model_objects = builder()
            receipt["models"].append(
                write_model(
                    root,
                    name,
                    model_objects,
                    camera_location=camera_location,
                    target=target,
                )
            )
        gallery = render_gallery(root)
        receipt["gallery"] = {
            "path": str(gallery),
            "bytes": gallery.stat().st_size,
            "sha256": sha256(gallery),
        }
        receipt["status"] = "generated"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = str(exc)
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["runtime_seconds"] = round(time.monotonic() - started, 3)
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

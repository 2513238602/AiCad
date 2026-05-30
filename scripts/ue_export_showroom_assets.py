import json
import os
import traceback

import unreal


OUT_DIR = r"G:\AiCad\web\public\assets\showroom-unreal"
MANIFEST_PATH = os.path.join(OUT_DIR, "manifest.json")

ASSETS = [
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Main_C",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Side_B",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Side_C",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Corner_B",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Corner_C",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_Curve_C",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_EdgeCurve_B",
    "/Game/AssetZoo/DemoRoom/Meshes/Display_EdgeCurve_C",
    "/Game/AssetZoo/DemoRoom/Meshes/ShadowBox_1MPanel",
    "/Game/AssetZoo/DemoRoom/Meshes/ShadowBox_1MPanel2",
    "/Game/AssetZoo/DemoRoom/Meshes/ShadowBox_RoundEdge",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Corner",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Corner_Bottom",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Corner_Top",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Side",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Side_Bottom",
    "/Game/AssetZoo/DemoRoom/Meshes/SM_DisplayFrame_Side_Top",
    "/Game/AssetZoo/DemoRoom/Meshes/Tile_10MWall",
    "/Game/AssetZoo/DemoRoom/Meshes/Tile_10MPillar_B_2",
    "/Game/AssetZoo/DemoRoom/Meshes/Floor_Corner",
    "/Game/AssetZoo/DemoRoom/Meshes/Floor_Edge",
    "/Game/AssetZoo/DemoRoom/Meshes/TrimFeature_MetalTrim_Straight_B",
    "/Game/AssetZoo/DemoRoom/Meshes/TrimFeature_MetalTrim_Bend_B",
]


def slug(asset_path):
    return asset_path.rsplit("/", 1)[-1] + ".glb"


def export_asset(asset_path, options):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        raise RuntimeError("Missing asset {}".format(asset_path))

    filename = os.path.join(OUT_DIR, slug(asset_path))
    ok = unreal.GLTFExporter.export_to_gltf(asset, filename, options, set())
    if not ok:
        raise RuntimeError("Export failed {}".format(asset_path))

    return {
        "name": asset_path.rsplit("/", 1)[-1],
        "source": asset_path,
        "url": "/assets/showroom-unreal/{}".format(slug(asset_path)),
        "bytes": os.path.getsize(filename),
    }


os.makedirs(OUT_DIR, exist_ok=True)

options = unreal.GLTFExportOptions()
options.export_uniform_scale = 0.01
options.export_preview_mesh = False
options.export_cameras = False
options.export_lights = False
options.export_vertex_colors = False

manifest = {
    "sourceProject": unreal.Paths.project_dir(),
    "assets": [],
    "errors": [],
}

for asset_path in ASSETS:
    try:
        row = export_asset(asset_path, options)
        manifest["assets"].append(row)
        unreal.log("AICAD_EXPORTED_GLTF {}".format(row["url"]))
    except Exception as exc:
        manifest["errors"].append(
            {
                "asset": asset_path,
                "error": str(exc),
                "trace": traceback.format_exc(),
            }
        )
        unreal.log_error("AICAD_EXPORT_FAILED {} {}".format(asset_path, exc))

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

unreal.log("AICAD_SHOWROOM_ASSET_MANIFEST={}".format(MANIFEST_PATH))
unreal.SystemLibrary.quit_editor()

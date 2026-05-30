import json
import os

import unreal


OUT_PATH = r"G:\AiCad\artifacts\showroom\ue_asset_probe.json"
SEARCH_PATHS = [
    "/Game/AssetZoo/DemoRoom",
    "/Game/CustomAssets",
    "/Game/Building",
    "/Game/ArchvisProject",
]


def class_name(asset_data):
    class_path = getattr(asset_data, "asset_class_path", None)
    if class_path:
        return str(class_path.asset_name)
    return str(asset_data.asset_class)


registry = unreal.AssetRegistryHelpers.get_asset_registry()
results = {
    "project": unreal.Paths.project_dir(),
    "has_gltf_export_options": hasattr(unreal, "GLTFExportOptions"),
    "has_gltf_static_mesh_exporter": hasattr(unreal, "GLTFStaticMeshExporter"),
    "paths": {},
}

for search_path in SEARCH_PATHS:
    rows = []
    for asset_data in registry.get_assets_by_path(search_path, recursive=True):
        asset_class = class_name(asset_data)
        if asset_class in {"StaticMesh", "Material", "MaterialInstanceConstant", "World"}:
            rows.append(
                {
                    "name": str(asset_data.asset_name),
                    "path": str(asset_data.package_name),
                    "class": asset_class,
                }
            )
    results["paths"][search_path] = rows[:240]

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

unreal.log("AICAD_UE_ASSET_PROBE={}".format(OUT_PATH))
unreal.SystemLibrary.quit_editor()

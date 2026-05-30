import json
import os

import unreal


OUT_PATH = r"G:\AiCad\artifacts\showroom\ue_gltf_api_probe.json"

names = [
    "GLTFExporter",
    "GLTFExportOptions",
    "GLTFLevelExporter",
    "GLTFStaticMeshExporter",
    "AssetExportTask",
    "Exporter",
]

data = {}
for name in names:
    obj = getattr(unreal, name, None)
    data[name] = sorted([item for item in dir(obj) if "export" in item.lower() or "option" in item.lower() or "task" in item.lower()]) if obj else None

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

unreal.log("AICAD_GLTF_API_PROBE={}".format(OUT_PATH))
unreal.SystemLibrary.quit_editor()

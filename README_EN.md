**English** | [中文](README.md)

# AiCad V2 - Cosmetic Packaging CAD Automation and Preview System

> V2 branch: parametric production CAD, image/VLM automation experiments, Gallery, and virtual showroom preview.  
> V1 is preserved on the `V1` branch. This branch is `V2`, and it is the current default branch.

---

## V2 Positioning

AiCad V2 is a working prototype for cosmetic packaging CAD automation, focused on lip gloss packaging components. It extends the V1 parametric CAD generator with image/VLM-assisted automation, Gallery workflows, early freeform/profile modeling experiments, and a web-based virtual showroom.

V2 is not the final product direction. It is the foundation for V3:

```text
V2: parameters / image analysis -> parametric CAD -> STEP/STL/SVG -> preview and showroom
V3: creative image -> AIGC 3D exterior shell -> AiCad production CAD reconstruction
```

---

## Main Changes From V1

- Added guide mode alongside advanced mode.
- Added VLM/CV automation pipeline for extracting appearance, proportions, and candidate CAD parameters from reference images.
- Added Gallery workflows for prebuilt/reference generation results.
- Added a virtual showroom entry and Three.js gallery corridor preview.
- Added profile/spline, exotic cap, mesh repair, and topology experiments.
- Enhanced engineering drawing generation with shared drawing primitives and projection helpers.
- Enhanced assembly, QC, repair, and render metadata modules.
- Preserved V1's four-component CAD generation, STEP/STL/SVG output, and assembly validation foundation.

---

## Current Capabilities

### Parametric CAD Components

Supported lip gloss packaging components:

- Bottle
- Cap
- Wiper
- Wand

Outputs:

- STEP for CAD and production communication
- STL for web preview
- SVG engineering drawings

### Advanced Mode and Guide Mode

- Advanced mode exposes the full parameter panel.
- Guide mode splits the workflow into product, component, core parameters, choice, fine tuning, and generation.

### Image/VLM Automation

V2 includes an early image automation pipeline:

- reference image classification
- appearance feature recognition
- silhouette/proportion/taper extraction
- Gallery-ready parameter output
- connection to the existing CadQuery generator

Key files:

- `scripts/auto_pipeline.py`
- `scripts/prebuild_gallery.py`
- `scripts/rebuild_gallery.py`
- `src/core/vlm_extract.py`
- `src/core/render_materials.py`

### Gallery and Virtual Showroom

V2 includes a Gallery page and a virtual showroom entry:

- Gallery for prebuilt/reference generation results
- Three.js corridor-style virtual showroom
- lightweight runtime GLB assets under `web/public/assets/`

Key files:

- `web/src/components/gallery/GalleryPage.vue`
- `web/src/components/showroom/ShowroomPage.vue`
- `web/public/assets/showroom-gallery/`
- `web/public/assets/showroom-unreal/`

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| CAD kernel | Python 3.11 + CadQuery 2.6.1 + OpenCASCADE |
| Backend | Python HTTP server, default port `8010` |
| Frontend | Vue 3 + TypeScript + Pinia + Element Plus |
| 3D rendering | Three.js 0.160 |
| Outputs | STEP / STL / SVG / JSON |
| Image pipeline | OpenCV + VLM adapters + parameter mapping |
| Showroom assets | GLB + Three.js runtime |

---

## Quick Start

### 0. One-Command Windows Reproduction

For a fresh Windows machine, start with:

- [docs/REPRODUCE_V2_WINDOWS.md](docs/REPRODUCE_V2_WINDOWS.md)

Bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1
```

Validate V2:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1
```

### Python

```bash
conda create -n AiCad python=3.11 -y
conda activate AiCad
pip install cadquery==2.6.1 aiohttp numpy ezdxf matplotlib opencv-python pillow requests
```

### Frontend

```bash
cd web
npm.cmd ci
npm.cmd run build
cd ..
```

### Start Web Server

```bash
python scripts/web_server.py --host 127.0.0.1 --port 8010
```

Open:

```text
http://127.0.0.1:8010/
```

On Windows:

```powershell
.\scripts\start.ps1
```

### CLI Smoke Test

```bash
python scripts/generate.py --product lip_gloss --component bottle --preset bottle_standard_5ml --outroot artifacts/v2_smoke
```

Generated files are written to `artifacts/`, which is ignored by Git.

---

## Blender Note

Some gallery/showroom asset generation workflows use Blender CLI. The Blender binary is not committed because it is too large.

Install Blender globally or place a local copy under `tools/blender/`. The folder is ignored by Git.

---

## Reports

- [V2 Release Notes](docs/V2_RELEASE_NOTES.md)
- [V2 Report Index](report/V2/README.md)
- [V3 AIGC to Production CAD Roadmap](report/V3/AiCad_V3_AIGC_to_Production_CAD.md)

---

## Verified Before Release

- `npm run build` passed
- Python core entry syntax check passed
- CLI generation produced STEP/STL/SVG
- Web API `/api/schema` and `/api/generate` returned JSON with `ok: true`

---

## Version Map

```text
V1: branch V1
V2: branch V2, current default branch
V3: roadmap only, not yet released as a branch
```

---

## License

Private project. All rights reserved.

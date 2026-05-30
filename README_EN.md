# AiCad V1 - Parametric CAD Generator for Lip Gloss Packaging

> V1 branch: the first runnable parametric industrial CAD prototype for lip gloss packaging.  
> This branch is fixed as AiCad V1. See the `V2` branch for the V2 release.

---

## V1 Positioning

AiCad V1 validates the basic idea of generating manufacturing-oriented CAD assets from structured parameters.

V1 focuses on four lip gloss packaging components:

- Bottle
- Cap
- Wiper
- Wand

Core outputs:

- STEP for CAD software and production communication
- STL for 3D preview
- SVG for engineering drawings

V1 focuses on deterministic CAD structure rather than complex exterior generation.

---

## Core Capabilities

- Parametric CAD generation for cap, bottle, wiper, and wand.
- Cross-component fit constraints and early assembly checks.
- STEP/STL/SVG export.
- Basic web UI with product/component selection, parameter panel, output panel, and 3D viewer.
- Bilingual UI foundation.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| CAD kernel | Python 3.11 + CadQuery 2.6.1 + OpenCASCADE |
| Backend | `scripts/web_server.py` |
| Frontend | Vue 3 + TypeScript + Pinia + Element Plus |
| 3D preview | Three.js |
| Outputs | STEP / STL / SVG / JSON |

---

## Quick Start

### Python

```bash
conda create -n AiCad python=3.11 -y
conda activate AiCad
pip install cadquery==2.6.1 aiohttp numpy ezdxf matplotlib
```

### Frontend

```bash
cd web
npm install
npm run build
cd ..
```

### Start Server

```bash
python scripts/web_server.py --host 127.0.0.1 --port 8010
```

Open:

```text
http://127.0.0.1:8010/
```

On Windows:

```powershell
.\scripts\run_web.ps1
```

### CLI Example

```bash
python scripts/generate.py --product lip_gloss --component cap --preset cap_full_detail_demo --outroot artifacts/cli
```

---

## V1 Boundaries

V1 does not include:

- VLM/CV image automation pipeline
- Gallery
- Virtual showroom
- Exotic exterior / mesh reconstruction experiments
- V3 AIGC exterior shell to production CAD workflow

Those belong to V2 or the V3 roadmap.

---

## Version Map

```text
V1: current branch
V2: V2 branch
```

---

## License

Private project. All rights reserved.

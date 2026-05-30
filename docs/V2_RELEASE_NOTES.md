# AiCad V2 Release Notes

## Positioning

AiCad V2 is the current integrated branch for a cosmetic packaging CAD generator. It combines deterministic parametric CAD generation with early image/VLM-assisted automation and a web-based preview/gallery experience.

The release target is practical continuity: after cloning the V2 branch and following setup instructions, a user should be able to run the web app, use guide/advanced modes, generate STEP/STL/SVG outputs, inspect models in the 3D viewer, and open the current gallery/showroom experience.

## Shipped Capabilities

- Parametric lip gloss packaging generator for cap, bottle, wiper, and wand.
- CadQuery/OpenCASCADE solid modeling and STEP export.
- STL preview export and SVG engineering drawing generation.
- Parameter schema, derived parameter rules, cross-component constraints, and component state management.
- Assembly positioning and QC/interference checks.
- Vue 3 web interface with guide mode, advanced mode, viewer modal, gallery, and virtual showroom entry.
- VLM/CV-assisted image-to-parameter pipeline experiments for gallery/reference-driven generation.
- Spline/profile and exotic cap experiments.
- Lightweight prebuilt showroom/gallery assets under `web/public`.

## Preserved Runtime Assets

The following are intended to be committed because they are needed for the current V2 user experience:

- `web/public/assets/showroom-gallery/`
- `web/public/assets/showroom-unreal/`
- `web/public/showroom/unreal/`
- selected sample/reference images under `tests/picture/`
- source scripts under `scripts/`
- source tests and diagnostic scripts under `tests/`

## Excluded Local Artifacts

The following are intentionally not part of the GitHub V2 release:

- `tools/blender/` local Blender installation
- `artifacts/webui/`, `artifacts/gallery_prebuilt/`, and other generated CAD outputs
- Chrome/browser profile caches under `artifacts/`
- generated test output folders such as `tests/a3_test_output/` and `tests/diag_output/`
- transient STL/STEP output files

Blender-dependent scripts remain in the repository, but the Blender binary is not committed. A fresh checkout can either install Blender globally or place a compatible Blender distribution under `tools/blender/` locally.

## Known V2 Limits

- Complex freeform exterior generation is not robust yet.
- Gallery/showroom quality is exploratory.
- The VLM/image pipeline helps with appearance and parameter extraction but is not yet a production-grade arbitrary exterior solver.
- Internal packaging structures exist as a working foundation but still require industrial refinement for broader mold-opening use.

## V3 Bridge

V3 starts from the V2 foundation and adds:

```text
creative image generation
-> AIGC 3D exterior shell
-> AppearanceIR
-> AiCad CAD reconstruction
-> production-oriented STEP/drawings/QC
```

See `report/V3/AiCad_V3_AIGC_to_Production_CAD.md`.

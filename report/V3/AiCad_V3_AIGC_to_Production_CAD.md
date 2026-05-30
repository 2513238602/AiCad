# AiCad V3: AIGC Exterior to Production CAD Workflow

## 1. North Star

AiCad V3 aims to combine AIGC's strong complex exterior generation with AiCad's deterministic industrial CAD pipeline.

The goal is not to generate a pretty mesh. The goal is to turn creative exterior ideas into production-oriented CAD data:

```text
creative image
-> AIGC 3D exterior shell
-> exterior analysis and reconstruction
-> AiCad production CAD
-> STEP, STL, engineering drawings, assembly checks, and manufacturability feedback
```

The final output must remain an engineering artifact that can support mold-opening communication: componentized geometry, internal structure, wall thickness logic, thread/interface definitions, fit constraints, drawings, and QC reports.

## 2. Core Product Thesis

Professional CAD engineers are not blocked by simple cylinders. They are blocked by complex exterior forms: sculpted caps, organic surfaces, irregular silhouettes, decorative reliefs, ribs, waves, grooves, and product-specific visual identity.

Current AIGC 3D products are good at visual exterior generation, but their output is usually only a mesh:

- no reliable wall thickness
- no real inner cavity
- no thread/interface standards
- no production component split
- no assembly relationship
- no engineering drawings
- no mold logic
- no trustworthy dimensions or tolerances

AiCad V3 should therefore use AIGC as an exterior generator and AiCad as the industrial reconstruction engine.

```text
AIGC owns visual imagination.
AiCad owns production truth.
```

## 3. V3 Primary Workflow

### Stage A: Creative Image Generation

Use Codex/OpenAI image generation, preferably `gpt-image-2` where available, to create cosmetic packaging concept images from product briefs.

Inputs:

- product type
- target market
- brand/style direction
- material direction
- required interface constraints such as neck standard, approximate volume, and component set

Outputs:

- 2D concept images
- multiple style candidates
- optional front/side/back/macro views for downstream 3D generation

V3 should keep generated images as `CreativeImage` assets, not as engineering sources.

### Stage B: AIGC 3D Exterior Shell Generation

Send selected concept images to one or more 3D AIGC providers:

- Tencent Hunyuan 3D
- Tripo/Tripo3D
- Hyper3D Rodin
- local Hunyuan3D or open-source alternatives where possible

Outputs:

- GLB/OBJ/STL exterior mesh
- PBR texture maps when available
- optional segmented parts, quad topology, and low-poly versions

The mesh is treated as an exterior reference shell, not a production CAD model.

### Stage C: Mesh Ingestion and Exterior Analysis

Use Blender CLI and local geometry analysis to normalize and inspect the AIGC mesh.

Required analysis:

- bounding box and scale normalization
- symmetry detection
- principal axes
- silhouette extraction from multiple views
- cross-section sampling
- segmentation into body/cap/decorative regions where possible
- surface defect detection
- manufacturability risk markers

Outputs:

- normalized mesh preview
- orthographic render set
- extracted silhouettes
- candidate feature regions
- confidence and failure diagnostics

### Stage D: AppearanceIR

Convert AIGC exterior information into a strict intermediate representation.

Example:

```json
{
  "product_type": "lip_gloss",
  "source": {
    "creative_image_id": "concept_001",
    "aigc_mesh_id": "shell_001",
    "provider": "hunyuan3d"
  },
  "outer_shell": {
    "class": "asymmetric_sculpted_cap",
    "symmetry": "partial_radial",
    "profile_mode": "spline_revolve_plus_local_relief",
    "profile_points": [[8.0, 0.0], [10.5, 18.0], [9.4, 55.0], [6.8, 76.0]]
  },
  "features": [
    {
      "type": "vertical_ribs",
      "region": "cap_outer_wall",
      "count": 36,
      "depth_mm": 0.35,
      "confidence": 0.78
    },
    {
      "type": "organic_relief",
      "region": "cap_front",
      "manufacturing_mode": "reference_rebuild",
      "confidence": 0.54
    }
  ],
  "interfaces": {
    "neck_standard": "18-415",
    "thread_required": true,
    "seal_required": true
  },
  "manufacturing_constraints": {
    "min_wall_mm": 0.8,
    "draft_deg_min": 1.0,
    "avoid_undercut": true
  }
}
```

AppearanceIR is the contract between the uncertain AIGC world and the deterministic CAD world.

### Stage E: CAD Reconstruction

AiCad compiles AppearanceIR into production CAD using CadQuery/OpenCASCADE.

Priority order:

1. Preserve industrial interfaces: neck, thread, seal, cavity, wand/wiper fit.
2. Rebuild the main exterior shell using CAD-native operations.
3. Rebuild decorations as manufacturable CAD features where possible.
4. Mark unsupported high-frequency sculptural detail as reference-only or require manual confirmation.
5. Run wall thickness, draft, undercut, assembly, and geometry QC.

CAD reconstruction modes:

- `revolved_spline`: for axisymmetric or near-axisymmetric packaging.
- `lofted_sections`: for non-circular but section-driven packaging.
- `feature_rebuild`: ribs, grooves, knurls, bands, labels, bevels, and controlled relief.
- `hybrid_reference`: AIGC mesh informs the exterior but does not become final STEP geometry.
- `manual_assist`: areas that cannot be made production-safe require user confirmation.

### Stage F: Production Output

Outputs:

- component STEP files
- STL preview files
- SVG engineering drawings
- assembly report
- manufacturability report
- render preview
- source traceability packet linking image, AIGC mesh, AppearanceIR, and final CAD

## 4. Implementation Milestones

### V3.0: AIGC Provider Benchmark

Goal: determine which provider best supports AiCad exterior reconstruction.

Tasks:

- collect 20-30 cosmetic packaging references, especially irregular forms
- run Hunyuan 3D, Tripo, and Rodin where available
- compare mesh quality, surface stability, back-side completion, symmetry, texture, export formats, API cost, latency, and failure modes
- store results in a provider-neutral format

Acceptance:

- one benchmark report
- one selected default provider
- one fallback provider
- cost table and quality scorecard

### V3.1: Creative Image Generation

Goal: generate controlled cosmetic packaging concept references.

Tasks:

- create prompt templates for product category, material, silhouette, component constraints, and style
- generate multi-view concept sheets
- store concept images and metadata
- prepare images for 3D generation providers

Acceptance:

- text prompt to 4-view concept sheet
- versioned creative assets
- manual selection UI or CLI

### V3.2: AIGC Mesh Ingestion

Goal: import provider meshes into AiCad without touching CAD reconstruction yet.

Tasks:

- provider adapters for Hunyuan/Tripo/Rodin
- download result assets
- normalize GLB/OBJ/STL with Blender CLI
- generate preview renders and metadata

Acceptance:

- one reference image produces one normalized mesh asset set
- assets are traceable and reproducible

### V3.3: AppearanceIR MVP

Goal: turn mesh and renders into structured exterior intent.

Tasks:

- silhouette extraction
- symmetry and axis detection
- profile point fitting
- feature candidate tagging
- confidence scoring

Acceptance:

- generated AppearanceIR validates against a JSON schema
- axisymmetric packaging can produce usable profile points

### V3.4: Production CAD Rebuild MVP

Goal: convert simple AIGC exterior references into real STEP.

Tasks:

- implement `revolved_spline` exterior builder
- connect exterior shell to existing bottle/cap internal structures
- preserve neck/thread/seal constraints
- generate drawings and QC

Acceptance:

- one AIGC-derived bottle/cap design exports STEP, STL, SVG, and QC
- final model is CAD-native, not mesh-as-STEP

### V3.5: Irregular Cap Shell

Goal: support sculpted cap exterior with standard internal production structure.

Tasks:

- classify sculpted exterior zones
- rebuild primary shell with loft/section features
- insert standard internal cavity/thread/seal
- detect unsupported undercuts and high-frequency sculptural details

Acceptance:

- one irregular cap concept becomes a manufacturability-reviewed CAD prototype

## 5. Provider Strategy

V3 should support both cloud API and local deployment.

Cloud API:

- faster validation
- best visual quality
- per-generation cost
- provider dependency and data egress

Local deployment:

- no API fee per generation
- better data control
- GPU and maintenance cost
- likely weaker than newest commercial cloud models

Recommended order:

1. Use cloud APIs for benchmark and early quality validation.
2. Build provider-neutral adapters so the project is not locked to one vendor.
3. Add local Hunyuan3D/open-source route once the AppearanceIR and CAD rebuild flow is proven.

## 6. Hard Boundaries

V3 must never silently treat AIGC mesh as production truth.

Rules:

- AIGC mesh is reference-only by default.
- Production STEP must be generated by AiCad's CAD kernel or a validated B-Rep reconstruction path.
- Engineering drawing dimensions must come from final CAD geometry, not AI text or mesh guesses.
- Internal structure must come from product standards and AiCad constraints.
- Any unsupported exterior feature must be reported with risk level.
- The user must be able to trace every final CAD decision back to input image, mesh, AppearanceIR, or engineering default.

## 7. Success Definition

AiCad V3 succeeds when it can take a visually complex cosmetic packaging idea and produce a production-oriented CAD package that includes:

- a visually faithful exterior
- a CAD-native outer shell
- real internal functional structures
- componentized assembly
- STEP files
- engineering drawings
- manufacturability and assembly checks
- clear warnings where the AI exterior cannot be safely translated

The strategic position is:

```text
Tripo/Hunyuan/Rodin generate attractive exterior references.
AiCad turns those references into production CAD.
```

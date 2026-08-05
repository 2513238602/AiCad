# AiCad

AiCad is a research prototype for reconstructing approximately axial and quasi-axial product meshes as compact, editable STEP/B-Rep solids. The project studies when a reconstruction is geometrically faithful, visually fair, structurally valid, and semantically editable—and when it should be rejected.

> Status: controlled research prototype. The public repository contains the V2 engineering codebase; the frozen research evidence package is being prepared for a separate, sanitised release. The system is not production-ready and no general AIGC-to-CAD claim is made.

## Problem

Triangle meshes are useful for visualisation, but they do not directly provide compact CAD topology or meaningful design controls. AiCad investigates a narrower, testable question: can an unlabelled product mesh be reconstructed as a valid STEP solid with a small semantic interface, while keeping geometry, silhouette, fairness, validity, and editability as separate acceptance criteria?

## Current Method

```text
triangle mesh
  -> normalisation and axis estimation
  -> periodic cross-section representation
  -> constrained B-spline side surface
  -> closed STEP/B-Rep solid
  -> six semantic edit controls
  -> geometry + silhouette + fairness + validity checks
```

The present method targets approximately axial and quasi-axial exteriors. It does not claim arbitrary-object reconstruction.

## Controlled Evaluation

- 30 procedural CAD-truth objects across 6 morphology classes
- 18 development objects and 12 once-used frozen test objects
- method, thresholds, and data manifests frozen before test evaluation
- no object-specific manual control-point adjustment

| Frozen measure | Result |
|---|---:|
| Geometry + silhouette gate | 11/12 objects |
| Geometry + silhouette + fairness gate | 10/12 objects |
| Median worst-direction P95 surface distance | 0.068983 mm |
| Minimum three-view silhouette IoU | 0.992184 |
| Single-parameter edit trials | 180 |
| Combined-parameter edit trials | 48 |
| Valid single solids after edits | 228/228 |

Each current output has three topological faces, 1,170 internal B-spline poles, and six user-facing semantic parameters. These quantities are reported separately: compact topology does not mean a trivial internal representation.

## Known Failures and Scope

- One tapered-rectangle case introduces an unintended lower ledge.
- One round case passes aggregate geometry and silhouette thresholds but fails longitudinal fairness.
- The controlled inputs are tessellated from procedural CAD truth, not sampled from real generative-model artefacts.
- Independent CAD/industrial-design evaluation, common-input external baselines, and physical validation are not yet complete.

Negative cases are retained as evidence. Aggregate distance scores are not used to override fairness or visual failure.

## Public V2 Codebase

The current public codebase includes parametric cosmetic-packaging components, STEP/STL/SVG export, assembly positioning, engineering-drawing experiments, an image-assisted parameter workflow, and a Vue/Three.js preview. These components provide engineering infrastructure for the reconstruction study; they are not presented as validation of the research claims above.

## Repository Structure

```text
src/       parametric CAD and engineering components
scripts/   generation and validation entry points
tests/     software and geometry checks
web/       browser-based engineering preview
docs/      technical and reproduction documentation
report/    project reports and roadmap material
```

## Research Output

N. Chen. “Compact Editable B-Rep Reconstruction from Unlabelled Product Meshes with Evidence-Gated Validation.” Manuscript in preparation, 2026; not submitted.

## Licence

No open-source licence is currently granted. The source is publicly viewable; reuse or redistribution requires permission from the author.


# AiCad V2 Report

AiCad V2 is the current working branch for a cosmetic packaging CAD generator. Its focus is to turn structured parameters and early image/VLM extraction results into manufacturing-oriented CAD assets.

## V2 Scope

- Parametric lip gloss packaging components: cap, bottle, wiper, and wand.
- CadQuery/OpenCASCADE-based solid generation.
- STEP/STL export and SVG engineering drawing output.
- Parameter schema, derived parameters, cross-component constraints, assembly positioning, and QC checks.
- Web UI with guide mode, advanced mode, 3D viewer, gallery, and virtual showroom entry.
- VLM/CV-assisted image pipeline for gallery and parameter extraction experiments.
- Early exotic/profile modeling experiments, including spline/profile controls and mesh repair tests.

## V2 Non-Goals

- V2 does not claim robust arbitrary freeform exterior generation.
- V2 does not convert AI-generated mesh directly into production STEP.
- V2 showroom/gallery quality is exploratory and should not be treated as final presentation quality.
- V2 internal structure is a foundation for production CAD, but still needs deeper industrial refinement.

## Release Principle

The V2 branch should be pullable from GitHub and runnable without losing current user-facing features. Generated outputs and local heavy toolchains should not be committed, but required source code, lightweight runtime assets, sample images, and setup instructions should be preserved.

# Sembiotic

Sembiotic is a private, deterministic biological meaning field running on ARBITER.

## Current production interface

- Clean fixed desktop composition with a non-overlapping stage and ranked rail.
- No decorative hero or background imagery.
- The selected media panel and result tiles display images only when the ranked source record contains explicit image metadata.
- Results without attached media remain honest, image-free records.
- Same-origin search at `/field/v1/search` and manifest at `/field/v1/manifest`.
- Runs on ARBITER: 26MB engine, 72D frozen geometry.

## Media policy

The server reads only `image_url`, `thumbnail_url`, `og_image`, `image`, or explicit `image_candidates` already attached to a field object or its metadata. It does not map unrelated microscopy imagery to results and does not generate scientific images.

## Deployment

Run `DEPLOY_SEMBIOTIC.command`. It resolves a NumPy-capable Python, validates the production HTML and record-only media policy, pushes to `git@github.com:ziolndr/sembiotic.git`, reinstalls the persistent field service, verifies local search, checks production, and opens `https://sembiotic.actualgeneralintelligence.com`.

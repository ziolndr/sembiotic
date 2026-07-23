# Sembiotic

ARBITER 72 biological meaning field.

ARBITER BIOLOGY — LOCAL FIELD PACKAGE
=====================================

WHAT CHANGED
The browser no longer sends the full candidate array to /v1/compare on every search.
The corpus is embedded once through the local ARBITER endpoint and stored as a persistent
normalized 72D field. A query embeds once, scans the local vector matrix, and returns ranked
biological objects with metadata.

PACKAGE CONTENTS
- public/index.html                     Field-backed ARBITER Biology interface
- corpus/base_actions.jsonl             168 curated objects from the original demo
- corpus/structured_seed.jsonl          12,000 labeled structured seed objects
- scripts/build_field.py                Resumable local /v1/embed field builder
- scripts/serve_field.py                Local search/manifest/frontend server
- scripts/ingest_sciencell.py            Public ScienCell catalog crawler
- scripts/import_jsonl.py                Import CSV, JSON, or JSONL private datasets
- INSTALL_AND_RUN.command               Build once, start field, open demo
- EXPAND_SCIENCELL_CATALOG.command       Crawl real public catalog pages and rebuild
- INSTALL_AUTOSTART.command             Keep the local field server alive through launchd

FIRST RUN
1. Make sure local ARBITER is running at http://127.0.0.1:8000/v1/embed
2. Double-click INSTALL_AND_RUN.command
3. The browser opens at http://127.0.0.1:8799

FIELD ENDPOINTS
GET  /field/v1/manifest
GET  /field/v1/health
POST /field/v1/search
     {"query":"...","mode":"omics","limit":42}

ADDING REAL DATA
Place normalized .jsonl files in corpus/ and run REBUILD_FIELD.command.
Each row should contain at minimum title and text. Useful optional fields:
id, code, category, domain, source, source_url, tenant, tags, metadata.

Generic import example:
python3 scripts/import_jsonl.py my_data.csv \
  --output corpus/illumina_private.jsonl \
  --source "Illumina private workspace" \
  --domain omics \
  --title-field sample_name \
  --text-field interpretation_text \
  --category-field assay_type

IMPORTANT DATA LABEL
structured_seed.jsonl is deliberately marked as generated_seed. It exercises scale and domain
coverage; it is not represented as a real ScienCell catalog or as patient evidence. Run the
ScienCell crawler and import validated private/public datasets to replace scale with real data.
Raw microscopy, omics, and laboratory files remain in archival storage; this field stores their
searchable semantic/operational representations and metadata, not reversible image compression.

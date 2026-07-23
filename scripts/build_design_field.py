#!/usr/bin/env python3

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sys
import time
import urllib.request

import numpy as np


ROOT = Path(sys.argv[1]).resolve()

SOURCE = "Sembiotic Design Field"
DOMAIN = "design"
CATEGORY = "Synthetic Design"
DESIGN_COUNT = 512
DIMENSION = 72


def excluded(path):
    parts = {part.lower() for part in path.parts}

    return bool(
        parts
        & {
            ".git",
            ".vercel",
            "backups",
            "node_modules",
            "__pycache__",
        }
    )


def count_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def locate_assets():
    manifests = []

    for path in ROOT.rglob("manifest.json"):
        if excluded(path):
            continue

        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue

        if (
            int(payload.get("dimension") or 0) == DIMENSION
            and int(payload.get("count") or 0) > 0
        ):
            manifests.append((path, payload))

    if not manifests:
        raise SystemExit("No active 72D manifest.json was found.")

    manifests.sort(
        key=lambda item: (
            item[1].get("status") == "ready",
            "biology" in str(item[0]).lower(),
            int(item[1].get("count") or 0),
            item[0].stat().st_mtime,
        ),
        reverse=True,
    )

    manifest_path, manifest = manifests[0]
    expected = int(manifest["count"])

    vectors = []

    for path in ROOT.rglob("vectors.npy"):
        if excluded(path):
            continue

        try:
            array = np.load(path, mmap_mode="r")
        except Exception:
            continue

        if array.ndim == 2 and array.shape[1] == DIMENSION:
            vectors.append((path, array.shape))

    if not vectors:
        raise SystemExit("No 72D vectors.npy was found.")

    vectors.sort(
        key=lambda item: (
            item[1][0] == expected,
            item[0].parent == manifest_path.parent,
            item[1][0],
            item[0].stat().st_mtime,
        ),
        reverse=True,
    )

    vectors_path, vector_shape = vectors[0]

    objects = []

    for filename in ("objects.jsonl", "metadata.jsonl"):
        for path in ROOT.rglob(filename):
            if excluded(path):
                continue

            try:
                rows = count_jsonl(path)
            except Exception:
                continue

            objects.append((path, rows))

    if not objects:
        raise SystemExit("No objects.jsonl or metadata.jsonl was found.")

    objects.sort(
        key=lambda item: (
            item[1] == vector_shape[0],
            item[0].parent == vectors_path.parent,
            item[1],
            item[0].stat().st_mtime,
        ),
        reverse=True,
    )

    objects_path, object_count = objects[0]

    if object_count != vector_shape[0]:
        raise SystemExit(
            f"Metadata/vector mismatch: "
            f"{object_count} rows vs {vector_shape[0]} vectors."
        )

    media_paths = [
        ROOT / "public" / "assets" / "media_catalog.json",
        ROOT / "public" / "media_catalog.json",
        ROOT / "assets" / "media_catalog.json",
        ROOT / "media_catalog.json",
    ]

    media_path = next(
        (path for path in media_paths if path.is_file()),
        None,
    )

    if media_path is None:
        media_path = next(
            (
                path
                for path in ROOT.rglob("media_catalog.json")
                if not excluded(path)
            ),
            None,
        )

    return (
        manifest_path,
        vectors_path,
        objects_path,
        media_path,
    )


def load_media_urls(media_path):
    if media_path is None:
        return []

    try:
        payload = json.loads(media_path.read_text())
    except Exception:
        return []

    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = (
            payload.get("media")
            or payload.get("items")
            or payload.get("records")
            or payload.get("results")
            or []
        )
    else:
        rows = []

    urls = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        url = (
            row.get("url")
            or row.get("image")
            or row.get("src")
            or row.get("image_url")
            or row.get("media_url")
        )

        if isinstance(url, str) and url.startswith("http"):
            urls.append(url)

    return list(dict.fromkeys(urls))


ARCHITECTURES = [
    (
        "fatty-acid vesicle",
        "a dynamic self-assembled membrane with rapid component exchange",
    ),
    (
        "phospholipid liposome",
        "a stable bilayer compartment with controlled permeability",
    ),
    (
        "polymer-lipid hybrid vesicle",
        "a durable membrane with tunable transport",
    ),
    (
        "coacervate-in-vesicle",
        "a dense catalytic interior inside a lipid boundary",
    ),
    (
        "lipid-coated coacervate",
        "a phase-separated core stabilized by an amphiphilic shell",
    ),
    (
        "double-membrane vesicle",
        "nested compartments separating incompatible chemistries",
    ),
    (
        "protein-stabilized vesicle",
        "a membrane reinforced by reversible structural peptides",
    ),
    (
        "hydrogel-core vesicle",
        "a structured interior that localizes catalysts and templates",
    ),
]

ENERGY = [
    (
        "light-driven proton gradient",
        "cyclic illumination is converted into an electrochemical gradient",
    ),
    (
        "redox cofactor loop",
        "electron transfer regenerates activated intermediates",
    ),
    (
        "substrate-level energy cycle",
        "chemical free energy is captured without a full respiratory chain",
    ),
    (
        "chemiosmotic module",
        "membrane potential drives internal chemical work",
    ),
    (
        "mineral-interface catalysis",
        "a catalytic surface sustains directional chemistry",
    ),
    (
        "thioester-like transfer network",
        "activated bond exchange moves energy through the system",
    ),
    (
        "nucleotide-triphosphate regeneration",
        "activated nucleotides are recycled from supplied precursors",
    ),
    (
        "activated-substrate pulse cycle",
        "periodic feeding is converted into bounded internal energy",
    ),
]

INFORMATION = [
    (
        "RNA template set",
        "heritable catalytic instructions are stored in short RNA templates",
    ),
    (
        "DNA-RNA hybrid genome",
        "durable storage is separated from active catalytic transcripts",
    ),
    (
        "peptide-nucleic-acid template",
        "information is stored in a chemically robust informational polymer",
    ),
    (
        "catalytic RNA network",
        "information is distributed across mutually supporting ribozymes",
    ),
    (
        "compositional genome",
        "membrane and catalyst ratios serve as inherited information",
    ),
    (
        "barcoded oligomer ensemble",
        "state is stored across a population of short polymers",
    ),
    (
        "minimal circular DNA",
        "a compact circular genome stores the functional program",
    ),
    (
        "compartment-state inheritance",
        "organization is transmitted through controlled partitioning",
    ),
]

REPLICATION = [
    "strand-displacement copying",
    "ligation-cycle replication",
    "ribozyme-assisted copying",
    "rolling-circle replication",
    "template-directed polymerization",
    "autocatalytic network replication",
    "compartment-coupled copying",
    "error-threshold-limited copying",
]

DIVISION = [
    "membrane-growth-driven fission",
    "osmotic budding",
    "lipid-phase-separation fission",
    "contractile peptide-ring division",
    "shear-assisted division",
    "thermal-cycle division",
    "microfluidic pinching validation",
    "spontaneous membrane pearling",
]

REGULATION = [
    "riboswitch feedback",
    "metabolite-gated catalysis",
    "phase-separation sequestration",
    "membrane-permeability feedback",
    "copy-number feedback",
    "catalytic inhibition",
    "resource-competition control",
    "selective degradation",
]

CONTAINMENT = [
    "external nutrient dependency",
    "narrow temperature gate",
    "synthetic cofactor dependency",
    "replication ceiling",
    "self-limiting error threshold",
    "supplied-lipid dependency",
    "dual-key activation",
    "noncanonical monomer dependency",
]

ENVIRONMENTS = [
    "neutral aqueous environment",
    "mild thermal cycling",
    "low-oxygen redox environment",
    "light-dark cycling",
    "mineral-surface interface",
    "salt-gradient chamber",
    "nutrient-pulse environment",
    "continuous-flow chamber",
]

READOUTS = [
    "membrane integrity and selective permeability",
    "energy-state persistence after feeding stops",
    "information-copy fidelity across generations",
    "balanced growth of boundary and interior",
    "daughter-compartment inheritance",
    "controlled phenotypic variation",
    "failure outside the permitted environment",
    "repeatability across independently assembled populations",
]


def build_candidates(media_urls):
    candidates = []

    for index in range(DESIGN_COUNT):
        architecture_index = index % 8
        energy_index = (index // 8) % 8
        information_index = (index // 64) % 8

        architecture = ARCHITECTURES[architecture_index]
        energy = ENERGY[energy_index]
        information = INFORMATION[information_index]

        replication = REPLICATION[
            (
                architecture_index
                + energy_index
                + information_index
            )
            % 8
        ]

        division = DIVISION[
            (
                architecture_index * 2
                + energy_index
                + information_index
            )
            % 8
        ]

        regulation = REGULATION[
            (
                architecture_index
                + energy_index * 2
                + information_index
            )
            % 8
        ]

        containment = CONTAINMENT[
            (
                architecture_index
                + energy_index
                + information_index * 2
            )
            % 8
        ]

        environment = ENVIRONMENTS[
            (
                architecture_index * 3
                + energy_index
                + information_index
            )
            % 8
        ]

        readout = READOUTS[index % len(READOUTS)]
        code = f"DESIGN-{index + 1:04d}"

        title = (
            f"{architecture[0].title()} · "
            f"{information[0].title()} · "
            f"{division.title()}"
        )

        text = (
            f"Synthetic life design candidate {code}. "
            f"Architecture: {architecture[0]}, {architecture[1]}. "
            f"Energy system: {energy[0]}, where {energy[1]}. "
            f"Information system: {information[0]}, where "
            f"{information[1]}. "
            f"Replication: {replication}. "
            f"Division: {division}. "
            f"Regulation: {regulation}. "
            f"Permitted environment: {environment}. "
            f"Containment: {containment}. "
            f"Primary validation readout: {readout}. "
            "The objective is to maintain a boundary, harvest energy, "
            "regulate internal chemistry, store and copy information, "
            "grow, divide, and undergo bounded controlled evolution. "
            "This is a conceptual design candidate for ranking and "
            "experimental prioritization, not a validated living system."
        )

        image = (
            media_urls[index % len(media_urls)]
            if media_urls
            else ""
        )

        candidate = {
            "id": code,
            "code": code,
            "name": title,
            "title": title,
            "text": text,
            "description": text,
            "summary": text,
            "domain": DOMAIN,
            "mode": DOMAIN,
            "category": CATEGORY,
            "subcategory": "Protocell Architecture",
            "source": SOURCE,
            "architecture": architecture[0],
            "energy_system": energy[0],
            "information_system": information[0],
            "replication_system": replication,
            "division_system": division,
            "regulation_system": regulation,
            "containment_system": containment,
            "environment": environment,
            "validation_readout": readout,
            "design_status": "conceptual candidate",
            "workflow": (
                "Generate → Embed → Rank → Build → Test → Iterate"
            ),
            "claim_boundary": (
                "ARBITER ranks coherence with the stated objective "
                "and candidate field. Synthesis and testing establish "
                "biological viability."
            ),
            "media_query": (
                "real microscopy of lipid vesicles, protocells, "
                "membranes, fluorescence assays, and compartment division"
            ),
        }

        if image:
            candidate.update(
                {
                    "image": image,
                    "image_url": image,
                    "media_url": image,
                    "thumbnail": image,
                    "poster": image,
                }
            )

        candidates.append(candidate)

    return candidates


def parse_embedding_response(payload, expected):
    vectors = None

    if isinstance(payload, list):
        vectors = payload

    elif isinstance(payload, dict):
        for key in ("vectors", "embeddings"):
            if isinstance(payload.get(key), list):
                vectors = payload[key]
                break

        if vectors is None and isinstance(payload.get("data"), list):
            rows = payload["data"]

            if rows and isinstance(rows[0], dict):
                vectors = [
                    row.get("embedding") or row.get("vector")
                    for row in rows
                ]
            else:
                vectors = rows

    array = np.asarray(vectors, dtype=np.float32)

    if array.shape != (expected, DIMENSION):
        raise RuntimeError(
            f"Expected {(expected, DIMENSION)}, received {array.shape}."
        )

    if not np.isfinite(array).all():
        raise RuntimeError("Non-finite embedding values returned.")

    norms = np.linalg.norm(array, axis=1, keepdims=True)

    if np.any(norms <= 1e-12):
        raise RuntimeError("Zero-length embedding returned.")

    return array / norms


def embed(url, texts):
    body = json.dumps(
        {
            "texts": texts,
            "use_freq": True,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SEMBIOTIC-DESIGN-FIELD/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        payload = json.loads(
            response.read().decode("utf-8")
        )

    return parse_embedding_response(
        payload,
        len(texts),
    )


(
    manifest_path,
    vectors_path,
    objects_path,
    media_path,
) = locate_assets()

print(f"manifest: {manifest_path}")
print(f"vectors:  {vectors_path}")
print(f"objects:  {objects_path}")
print(f"media:    {media_path or 'none'}")

manifest = json.loads(manifest_path.read_text())
embedding_url = str(
    manifest.get("embedding_url")
    or "http://127.0.0.1:8000/v1/embed"
).strip()

objects = []

with objects_path.open(
    "r",
    encoding="utf-8",
) as handle:
    for line_number, line in enumerate(handle, 1):
        line = line.strip()

        if not line:
            continue

        try:
            objects.append(json.loads(line))
        except Exception as error:
            raise SystemExit(
                f"Invalid JSON at line {line_number}: {error}"
            )

vectors = np.load(vectors_path)

if vectors.ndim != 2 or vectors.shape[1] != DIMENSION:
    raise SystemExit(
        f"Unexpected vector shape: {vectors.shape}"
    )

if len(objects) != vectors.shape[0]:
    raise SystemExit(
        f"Existing mismatch: {len(objects)} objects "
        f"vs {vectors.shape[0]} vectors."
    )

keep = np.asarray(
    [
        row.get("source") != SOURCE
        and row.get("domain") != DOMAIN
        for row in objects
    ],
    dtype=bool,
)

removed = int((~keep).sum())

if removed:
    vectors = vectors[keep]
    objects = [
        row
        for row, retain in zip(objects, keep)
        if retain
    ]

    print(
        f"removed previous design field: {removed:,}"
    )

media_urls = load_media_urls(media_path)
candidates = build_candidates(media_urls)

batches = []
batch_size = 32

for start in range(
    0,
    len(candidates),
    batch_size,
):
    batch = candidates[start : start + batch_size]
    texts = [row["text"] for row in batch]
    last_error = None

    for attempt in range(1, 4):
        try:
            batches.append(
                embed(
                    embedding_url,
                    texts,
                )
            )

            last_error = None
            break

        except Exception as error:
            last_error = error

            if attempt < 3:
                time.sleep(attempt * 2)

    if last_error:
        raise SystemExit(
            f"Embedding failed at rows "
            f"{start + 1}-{start + len(batch)}: "
            f"{last_error}"
        )

    print(
        f"embedded "
        f"{min(start + batch_size, len(candidates)):,}"
        f"/{len(candidates):,}"
    )

design_vectors = np.vstack(batches).astype(
    np.float32,
    copy=False,
)

combined_vectors = np.vstack(
    [
        np.asarray(vectors, dtype=np.float32),
        design_vectors,
    ]
)

combined_objects = objects + candidates

vectors_temp = vectors_path.with_name(
    vectors_path.name + ".design.tmp"
)

objects_temp = objects_path.with_name(
    objects_path.name + ".design.tmp"
)

manifest_temp = manifest_path.with_name(
    manifest_path.name + ".design.tmp"
)

with vectors_temp.open("wb") as handle:
    np.save(
        handle,
        combined_vectors,
        allow_pickle=False,
    )

with objects_temp.open(
    "w",
    encoding="utf-8",
) as handle:
    for row in combined_objects:
        handle.write(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

domains = Counter(
    str(
        row.get("domain")
        or row.get("mode")
        or "unknown"
    )
    for row in combined_objects
)

categories = Counter(
    str(
        row.get("category")
        or "Uncategorized"
    )
    for row in combined_objects
)

sources = Counter(
    str(
        row.get("source")
        or "unknown"
    )
    for row in combined_objects
)

fingerprint = sha256()

for source_path in (
    vectors_temp,
    objects_temp,
):
    with source_path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            fingerprint.update(chunk)

now = datetime.now(timezone.utc)

manifest.update(
    {
        "status": "ready",
        "version": now.strftime(
            "%Y%m%dT%H%M%SZ"
        ),
        "count": len(combined_objects),
        "dimension": DIMENSION,
        "built_at": now.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "domains": dict(domains),
        "categories": dict(categories),
        "sources": dict(sources),
        "vector_bytes": vectors_temp.stat().st_size,
        "metadata_bytes": objects_temp.stat().st_size,
        "corpus_fingerprint": fingerprint.hexdigest(),
        "design_field": {
            "status": "ready",
            "count": len(candidates),
            "domain": DOMAIN,
            "category": CATEGORY,
            "source": SOURCE,
            "workflow": (
                "Generate → Embed → Rank → Build → Test → Iterate"
            ),
            "claim_boundary": (
                "Meaning selects the design. "
                "Experiment decides whether it lives."
            ),
        },
    }
)

manifest_temp.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    )
    + "\n"
)

os.replace(
    vectors_temp,
    vectors_path,
)

os.replace(
    objects_temp,
    objects_path,
)

os.replace(
    manifest_temp,
    manifest_path,
)

print()
print(
    f"Design Field written: "
    f"{len(candidates):,} candidates"
)

print(
    f"Total field: "
    f"{len(combined_objects):,} objects · 72D"
)

print(
    f"Real media URLs assigned: "
    f"{len(media_urls):,}"
)

#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, RLock, Thread
from typing import Any
from urllib.parse import urlparse
import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import time

import numpy as np


PAGE_SIZE = 50
RANKING_CACHE_SIZE = 16
QUERY_CACHE_SIZE = 128
EXPANSION_SCAN_SECONDS = 15

MODE_BITS = {
    "design": 1 << 0,
    "molecular_diagnostics": 1 << 1,
    "cells": 1 << 2,
    "pathways": 1 << 3,
    "images": 1 << 4,
    "assays": 1 << 5,
    "papers": 1 << 6,
    "products": 1 << 7,
    "experiments": 1 << 8,
    "operations": 1 << 9,
}

MODE_ALIASES = {
    "": "unified",
    "all": "unified",
    "everything": "unified",
    "unified": "unified",
    "designs": "design",
    "design field": "design",
    "design fields": "design",
    "moldx": "molecular_diagnostics",
    "molecular diagnostics": "molecular_diagnostics",
    "molecular-diagnostics": "molecular_diagnostics",
    "cell": "cells",
    "pathway": "pathways",
    "image": "images",
    "imaging": "images",
    "assay": "assays",
    "paper": "papers",
    "product": "products",
    "experiment": "experiments",
    "operation": "operations",
}

TERMS = {
    "design": (
        "sembiotic design field",
        "protocell",
        "synthetic life",
        "candidate architecture",
        "membrane architecture",
    ),
    "molecular_diagnostics": (
        "molecular diagnostic",
        "molecular diagnostics",
        "cell-free dna",
        "cell free dna",
        "cfdna",
        "ctdna",
        "liquid biopsy",
        "prenatal screening",
        "noninvasive prenatal",
        "nipt",
        "aneuploid",
        "microdeletion",
        "fetal fraction",
        "molecular counting",
        "genomic profiling",
        "genetic testing",
        "variant detection",
        "sequencing assay",
        "diagnostic assay",
        "clinvar",
        "pcr",
        "qpcr",
        "ddpcr",
        "digital pcr",
        "biomarker",
        "minimal residual disease",
        "fragmentomics",
        "methylation",
    ),
    "cells": (
        " cell ",
        "cells",
        "neuron",
        "astrocyte",
        "microglia",
        "stem cell",
        "organoid",
        "cell line",
        "trophoblast",
    ),
    "pathways": (
        "pathway",
        "signaling",
        "mechanism",
        "metabolic network",
        "gene network",
    ),
    "images": (
        "image",
        "imaging",
        "microscopy",
        "morphology",
        "fluorescence",
        "confocal",
        "spatial",
    ),
    "assays": (
        "assay",
        "qpcr",
        "pcr",
        "reporter",
        "readout",
        "screening test",
        "panel",
    ),
    "papers": (
        "publication",
        "journal",
        "paper",
        "study",
        "pubmed",
        "openalex",
    ),
    "products": (
        "product",
        "reagent",
        "kit",
        "catalog",
        "vector",
        "antibody",
    ),
    "experiments": (
        "experiment",
        "protocol",
        "validation",
        "control",
        "perturbation",
        "model system",
    ),
    "operations": (
        "operation",
        "inventory",
        "cold chain",
        "shipping",
        "quality",
        "capa",
        "logistics",
        "vendor",
    ),
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalized_mode(value: Any) -> str:
    value = clean(value).lower()
    return MODE_ALIASES.get(value, value)


def nested_strings(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from nested_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_strings(child)
    elif isinstance(value, str):
        yield value


def compact_blob(row: dict[str, Any]) -> str:
    values = []

    for key in (
        "title",
        "name",
        "label",
        "text",
        "description",
        "summary",
        "abstract",
        "category",
        "type",
        "object_type",
        "domain",
        "subdomain",
        "source",
        "keywords",
        "conditions",
        "genes",
        "modality",
        "specimen",
        "analyte",
    ):
        value = row.get(key)

        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))

    metadata = row.get("metadata")

    if isinstance(metadata, dict):
        for key in (
            "title",
            "description",
            "category",
            "type",
            "domain",
            "source",
            "keywords",
            "conditions",
            "genes",
        ):
            value = metadata.get(key)

            if isinstance(value, list):
                values.extend(str(item) for item in value)
            elif value is not None:
                values.append(str(value))

    return clean(" ".join(values)).lower()


def mode_mask(row: dict[str, Any]) -> int:
    blob = " " + compact_blob(row) + " "
    mask = 0

    domain = normalized_mode(
        row.get("sembiotic_domain")
        or row.get("domain")
        or row.get("mode")
    )

    if domain in MODE_BITS:
        mask |= MODE_BITS[domain]

    if clean(row.get("source")).lower() == "sembiotic design field":
        mask |= MODE_BITS["design"]

    for mode, terms in TERMS.items():
        if any(term in blob for term in terms):
            mask |= MODE_BITS[mode]

    return mask


def stable_id(row: dict[str, Any], fallback: str) -> str:
    value = (
        row.get("id")
        or row.get("code")
        or row.get("identifier")
        or row.get("doi")
        or row.get("pmid")
        or row.get("nct_id")
        or row.get("variation_id")
        or row.get("url")
        or row.get("source_url")
    )

    if value:
        return str(value)

    raw = (
        clean(row.get("title") or row.get("name"))
        + "\n"
        + clean(row.get("source"))
        + "\n"
        + fallback
    )

    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def recursive_strings(payload: Any):
    if isinstance(payload, dict):
        for value in payload.values():
            yield from recursive_strings(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from recursive_strings(value)
    elif isinstance(payload, str):
        yield payload


def vector_rows(path: Path, dimension: int) -> int:
    if path.suffix.lower() == ".npy":
        array = np.load(path, mmap_mode="r")

        if array.ndim != 2 or array.shape[1] != dimension:
            return 0

        return int(array.shape[0])

    size = path.stat().st_size
    width = dimension * 4

    if size <= 0 or size % width:
        return 0

    return size // width


def resolve_declared(
    manifest_path: Path,
    manifest: dict[str, Any],
    suffixes: tuple[str, ...],
) -> list[Path]:
    output = []
    seen = set()

    for value in recursive_strings(manifest):
        if not value.lower().endswith(suffixes):
            continue

        source = Path(value).expanduser()

        for candidate in (
            source,
            manifest_path.parent / source,
            manifest_path.parent / source.name,
        ):
            try:
                candidate = candidate.resolve()
            except Exception:
                continue

            if candidate in seen:
                continue

            seen.add(candidate)

            if candidate.is_file():
                output.append(candidate)

    return output


def resolve_bundle(
    manifest_path: Path,
) -> tuple[dict[str, Any], Path, Path]:
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    dimension = int(
        manifest.get("dimension")
        or manifest.get("dim")
        or 72
    )

    count = int(
        manifest.get("count")
        or manifest.get("object_count")
        or 0
    )

    vector_candidates = resolve_declared(
        manifest_path,
        manifest,
        (".f32", ".npy", ".bin"),
    )

    for name in (
        "vectors.f32",
        "vectors.npy",
        "embeddings.f32",
        "matrix.f32",
        "vectors.bin",
    ):
        candidate = manifest_path.parent / name

        if candidate.is_file():
            vector_candidates.append(candidate)

    vector_candidates = list(
        dict.fromkeys(vector_candidates)
    )

    vector_candidates = [
        candidate
        for candidate in vector_candidates
        if vector_rows(candidate, dimension) > 0
    ]

    if not vector_candidates:
        raise RuntimeError(
            f"No vector file for {manifest_path}"
        )

    vector_candidates.sort(
        key=lambda path: (
            vector_rows(path, dimension) == count,
            vector_rows(path, dimension),
            path.stat().st_mtime,
        ),
        reverse=True,
    )

    vectors_path = vector_candidates[0]
    actual_count = vector_rows(
        vectors_path,
        dimension,
    )

    metadata_candidates = resolve_declared(
        manifest_path,
        manifest,
        (".jsonl", ".ndjson"),
    )

    for name in (
        "metadata.jsonl",
        "objects.jsonl",
        "records.jsonl",
        "rows.jsonl",
    ):
        candidate = manifest_path.parent / name

        if candidate.is_file():
            metadata_candidates.append(candidate)

    metadata_candidates = list(
        dict.fromkeys(metadata_candidates)
    )

    if not metadata_candidates:
        raise RuntimeError(
            f"No metadata JSONL for {manifest_path}"
        )

    preferred = {
        "metadata.jsonl": 4,
        "objects.jsonl": 3,
        "records.jsonl": 2,
        "rows.jsonl": 1,
    }

    metadata_candidates.sort(
        key=lambda path: (
            preferred.get(path.name, 0),
            path.stat().st_size,
        ),
        reverse=True,
    )

    metadata_path = metadata_candidates[0]

    manifest["count"] = actual_count
    manifest["dimension"] = dimension

    return manifest, vectors_path, metadata_path


@dataclass
class MetadataStore:
    path: Path
    offsets: np.ndarray
    masks: np.ndarray
    handle: Any
    lock: Lock

    @classmethod
    def load(cls, path: Path):
        offsets = []
        masks = []
        position = 0

        with path.open("rb") as handle:
            for line in handle:
                if line.strip():
                    offsets.append(position)

                    try:
                        row = json.loads(
                            line.decode(
                                "utf-8",
                                errors="replace",
                            )
                        )

                        if not isinstance(row, dict):
                            row = {"text": str(row)}

                    except Exception:
                        row = {}

                    masks.append(mode_mask(row))

                position += len(line)

        return cls(
            path=path,
            offsets=np.asarray(
                offsets,
                dtype=np.int64,
            ),
            masks=np.asarray(
                masks,
                dtype=np.uint16,
            ),
            handle=path.open("rb"),
            lock=Lock(),
        )

    def read(self, index: int) -> dict[str, Any]:
        with self.lock:
            self.handle.seek(
                int(self.offsets[index])
            )
            line = self.handle.readline()

        row = json.loads(
            line.decode(
                "utf-8",
                errors="replace",
            )
        )

        if not isinstance(row, dict):
            row = {"text": str(row)}

        return row


@dataclass
class Shard:
    key: str
    source: str
    vectors_path: Path
    metadata_path: Path
    vectors: np.ndarray
    metadata: MetadataStore

    @property
    def count(self) -> int:
        return int(self.vectors.shape[0])

    def indexes(self, mode: str) -> np.ndarray:
        mode = normalized_mode(mode)
        bit = MODE_BITS.get(mode)

        if bit is None:
            return np.arange(
                self.count,
                dtype=np.int32,
            )

        return np.flatnonzero(
            self.metadata.masks & bit
        ).astype(np.int32)


class EmbeddingClient:
    def __init__(self, url: str):
        self.url = url
        self.parsed = urlparse(url)
        self.connection = None
        self.lock = Lock()
        self.cache: OrderedDict[
            str,
            np.ndarray,
        ] = OrderedDict()

    def connect(self):
        if self.parsed.scheme == "https":
            self.connection = (
                http.client.HTTPSConnection(
                    self.parsed.hostname,
                    self.parsed.port or 443,
                    timeout=60,
                )
            )
        else:
            self.connection = (
                http.client.HTTPConnection(
                    self.parsed.hostname,
                    self.parsed.port or 80,
                    timeout=60,
                )
            )

    @staticmethod
    def parse(payload: Any) -> np.ndarray:
        values = None

        if isinstance(payload, list):
            values = payload

        elif isinstance(payload, dict):
            values = (
                payload.get("vectors")
                or payload.get("embeddings")
            )

            if (
                values is None
                and isinstance(
                    payload.get("data"),
                    list,
                )
            ):
                data = payload["data"]

                if (
                    data
                    and isinstance(data[0], dict)
                ):
                    values = [
                        item.get("embedding")
                        or item.get("vector")
                        for item in data
                    ]
                else:
                    values = data

        array = np.asarray(
            values,
            dtype=np.float32,
        )

        if array.shape == (1, 72):
            array = array[0]

        if array.shape != (72,):
            raise RuntimeError(
                f"Embedding shape was {array.shape}"
            )

        norm = float(np.linalg.norm(array))

        if norm <= 1e-12:
            raise RuntimeError(
                "Embedding norm was zero"
            )

        return array / norm

    def embed(
        self,
        text: str,
    ) -> tuple[np.ndarray, bool]:
        key = clean(text)

        cached = self.cache.get(key)

        if cached is not None:
            self.cache.move_to_end(key)
            return cached, True

        body = json.dumps(
            {
                "texts": [key],
                "use_freq": True,
            },
            separators=(",", ":"),
        ).encode()

        path = self.parsed.path or "/"

        if self.parsed.query:
            path += "?" + self.parsed.query

        with self.lock:
            last_error = None

            for _attempt in range(2):
                try:
                    if self.connection is None:
                        self.connect()

                    self.connection.request(
                        "POST",
                        path,
                        body=body,
                        headers={
                            "Content-Type":
                                "application/json",
                            "Accept":
                                "application/json",
                            "Connection":
                                "keep-alive",
                            "User-Agent":
                                "SEMBIOTIC-FAST-FIELD/1.0",
                        },
                    )

                    response = (
                        self.connection.getresponse()
                    )

                    raw = response.read()

                    if response.status >= 400:
                        raise RuntimeError(
                            f"Embed HTTP "
                            f"{response.status}: "
                            f"{raw[:500]!r}"
                        )

                    vector = self.parse(
                        json.loads(raw)
                    )

                    break

                except Exception as error:
                    last_error = error

                    try:
                        if self.connection:
                            self.connection.close()
                    except Exception:
                        pass

                    self.connection = None

            else:
                raise RuntimeError(
                    f"Embedding failed: {last_error}"
                )

        self.cache[key] = vector
        self.cache.move_to_end(key)

        while len(self.cache) > QUERY_CACHE_SIZE:
            self.cache.popitem(last=False)

        return vector, False


class FastField:
    def __init__(
        self,
        root: Path,
        embed_url: str,
    ):
        self.root = root.resolve()
        self.expansion_root = (
            self.root
            / "field_expansion"
            / "molecular_diagnostics"
            / "shards"
        )

        self.embedder = EmbeddingClient(
            embed_url
        )

        self.lock = RLock()
        self.shards: list[Shard] = []
        self.loaded_manifests = set()
        self.generation = 0
        self.ranking_cache: OrderedDict[
            str,
            dict[str, Any],
        ] = OrderedDict()
        self.started = time.time()
        self.media = self.load_media()

        self.load_base()
        self.reload_expansion()

        Thread(
            target=self.watch_expansion,
            daemon=True,
        ).start()

        try:
            vector, _cached = self.embedder.embed(
                "molecular diagnostics warm field"
            )

            for shard in self.shards:
                if shard.count:
                    _ = float(
                        shard.vectors[:1] @ vector
                    )

        except Exception as error:
            print(
                f"warmup warning: {error}",
                flush=True,
            )

    def load_media(self):
        candidates = [
            self.root
            / "public"
            / "assets"
            / "media_catalog.json",
            self.root
            / "public"
            / "media_catalog.json",
            self.root
            / "media_catalog.json",
        ]

        for path in candidates:
            if not path.is_file():
                continue

            try:
                payload = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(payload, dict):
                    payload = (
                        payload.get("media")
                        or payload.get("items")
                        or payload.get("records")
                        or payload.get("results")
                        or []
                    )

                rows = []

                for item in payload:
                    if isinstance(item, str):
                        item = {"url": item}

                    if not isinstance(item, dict):
                        continue

                    metadata = (
                        item.get("metadata")
                        if isinstance(
                            item.get("metadata"),
                            dict,
                        )
                        else {}
                    )

                    url = ""

                    for key in (
                        "image",
                        "image_url",
                        "media_url",
                        "url",
                        "src",
                        "thumbnail",
                        "full",
                        "original",
                    ):
                        candidate = clean(
                            item.get(key)
                            or metadata.get(key)
                        )

                        if candidate.startswith(
                            ("http://", "https://")
                        ):
                            url = candidate
                            break

                    if not url:
                        continue

                    text = clean(
                        " ".join(
                            nested_strings(item)
                        )
                    ).lower()

                    rows.append(
                        {
                            "url": url,
                            "title": clean(
                                item.get("title")
                                or item.get("name")
                            ),
                            "caption": clean(
                                item.get("caption")
                                or item.get(
                                    "description"
                                )
                            ),
                            "credit": clean(
                                item.get("credit")
                                or item.get(
                                    "attribution"
                                )
                            ),
                            "source_url": clean(
                                item.get("source_url")
                                or item.get(
                                    "credit_url"
                                )
                            ),
                            "terms": set(
                                re.findall(
                                    r"[a-z0-9_-]{3,}",
                                    text,
                                )
                            ),
                        }
                    )

                return rows

            except Exception:
                continue

        return []

    @staticmethod
    def load_vectors(
        path: Path,
        count: int,
    ) -> np.ndarray:
        if path.suffix.lower() == ".npy":
            vectors = np.asarray(
                np.load(path, mmap_mode="r"),
                dtype=np.float32,
            )
        else:
            vectors = np.asarray(
                np.memmap(
                    path,
                    mode="r",
                    dtype="<f4",
                    shape=(count, 72),
                ),
                dtype=np.float32,
            )

        vectors = np.ascontiguousarray(vectors)

        sample = vectors[
            : min(len(vectors), 4096)
        ]

        norms = np.linalg.norm(
            sample,
            axis=1,
        )

        median = float(np.median(norms))

        if not 0.985 <= median <= 1.015:
            full_norms = np.linalg.norm(
                vectors,
                axis=1,
                keepdims=True,
            )

            vectors = vectors / np.maximum(
                full_norms,
                1e-12,
            )

            vectors = np.ascontiguousarray(
                vectors,
                dtype=np.float32,
            )

        return vectors

    def make_shard(
        self,
        key: str,
        source: str,
        vectors_path: Path,
        metadata_path: Path,
        count: int,
    ) -> Shard:
        vectors = self.load_vectors(
            vectors_path,
            count,
        )

        metadata = MetadataStore.load(
            metadata_path
        )

        if len(metadata.offsets) != len(vectors):
            raise RuntimeError(
                f"Metadata/vector mismatch in {key}: "
                f"{len(metadata.offsets)} vs "
                f"{len(vectors)}"
            )

        return Shard(
            key=key,
            source=source,
            vectors_path=vectors_path,
            metadata_path=metadata_path,
            vectors=vectors,
            metadata=metadata,
        )

    def load_base(self):
        candidates = []

        for manifest_path in self.root.rglob(
            "manifest.json"
        ):
            lowered = {
                part.lower()
                for part in manifest_path.parts
            }

            if {
                ".git",
                "backups",
                "node_modules",
                "field_expansion",
            } & lowered:
                continue

            try:
                manifest = json.loads(
                    manifest_path.read_text(
                        encoding="utf-8"
                    )
                )

                count = int(
                    manifest.get("count")
                    or manifest.get(
                        "object_count"
                    )
                    or 0
                )

                dimension = int(
                    manifest.get("dimension")
                    or manifest.get("dim")
                    or 0
                )

                if count > 0 and dimension == 72:
                    candidates.append(
                        (
                            count,
                            manifest_path.stat().st_mtime,
                            manifest_path,
                        )
                    )

            except Exception:
                continue

        if not candidates:
            raise RuntimeError(
                "No base Sembiotic 72D manifest found"
            )

        candidates.sort(reverse=True)
        _count, _mtime, manifest_path = (
            candidates[0]
        )

        manifest, vectors_path, metadata_path = (
            resolve_bundle(manifest_path)
        )

        shard = self.make_shard(
            key="base",
            source="sembiotic_base",
            vectors_path=vectors_path,
            metadata_path=metadata_path,
            count=int(manifest["count"]),
        )

        self.shards.append(shard)
        self.loaded_manifests.add(
            str(manifest_path.resolve())
        )

        print(
            f"base field · {shard.count:,} objects · "
            f"{vectors_path}",
            flush=True,
        )

    def reload_expansion(self):
        if not self.expansion_root.is_dir():
            return

        new_shards = []

        for manifest_path in sorted(
            self.expansion_root.glob(
                "shard-*/manifest.json"
            )
        ):
            key = str(manifest_path.resolve())

            if key in self.loaded_manifests:
                continue

            try:
                manifest, vectors_path, metadata_path = (
                    resolve_bundle(manifest_path)
                )

                shard = self.make_shard(
                    key=key,
                    source=clean(
                        manifest.get("source")
                        or "molecular_diagnostics"
                    ),
                    vectors_path=vectors_path,
                    metadata_path=metadata_path,
                    count=int(manifest["count"]),
                )

                new_shards.append(
                    (
                        key,
                        shard,
                    )
                )

            except Exception as error:
                print(
                    f"expansion shard skipped · "
                    f"{manifest_path} · {error}",
                    flush=True,
                )

        if not new_shards:
            return

        with self.lock:
            for key, shard in new_shards:
                self.shards.append(shard)
                self.loaded_manifests.add(key)

                print(
                    f"expansion loaded · "
                    f"{shard.count:,} · "
                    f"{Path(key).parent.name}",
                    flush=True,
                )

            self.generation += 1
            self.ranking_cache.clear()

    def watch_expansion(self):
        while True:
            time.sleep(
                EXPANSION_SCAN_SECONDS
            )

            try:
                self.reload_expansion()
            except Exception as error:
                print(
                    f"expansion watcher: {error}",
                    flush=True,
                )

    @property
    def count(self) -> int:
        with self.lock:
            return sum(
                shard.count
                for shard in self.shards
            )

    def source_counts(self):
        with self.lock:
            counts = Counter()

            for shard in self.shards:
                counts[shard.source] += (
                    shard.count
                )

            return dict(counts)

    def manifest(self):
        with self.lock:
            design_count = 0
            moldx_count = 0

            for shard in self.shards:
                design_count += int(
                    np.count_nonzero(
                        shard.metadata.masks
                        & MODE_BITS["design"]
                    )
                )

                moldx_count += int(
                    np.count_nonzero(
                        shard.metadata.masks
                        & MODE_BITS[
                            "molecular_diagnostics"
                        ]
                    )
                )

            return {
                "status": "ready",
                "count": self.count,
                "dimension": 72,
                "dim": 72,
                "score_mode":
                    "normalized dot product",
                "server":
                    "sembiotic-fast-field",
                "generation":
                    self.generation,
                "sources":
                    self.source_counts(),
                "design_field": {
                    "status":
                        "ready"
                        if design_count
                        else "missing",
                    "count":
                        design_count,
                },
                "molecular_diagnostics": {
                    "status":
                        "ready"
                        if moldx_count
                        else "building",
                    "count":
                        moldx_count,
                    "target":
                        300000,
                },
                "pagination": {
                    "page_size":
                        PAGE_SIZE,
                    "ranking_limit":
                        None,
                    "stable_ranking":
                        True,
                },
                "transport": {
                    "in_memory":
                        True,
                    "persistent_embedding":
                        True,
                    "query_cache":
                        True,
                    "ranking_cache":
                        True,
                },
                "uptime_seconds":
                    round(
                        time.time()
                        - self.started,
                        3,
                    ),
            }

    def ranking_key(
        self,
        query: str,
        mode: str,
    ) -> str:
        return hashlib.sha256(
            (
                str(self.generation)
                + "\n"
                + normalized_mode(mode)
                + "\n"
                + clean(query)
            ).encode()
        ).hexdigest()

    @staticmethod
    def encode_cursor(
        ranking_id: str,
        offset: int,
    ) -> str:
        raw = json.dumps(
            {
                "ranking_id":
                    ranking_id,
                "offset":
                    int(offset),
            },
            separators=(",", ":"),
        ).encode()

        return base64.urlsafe_b64encode(
            raw
        ).decode().rstrip("=")

    @staticmethod
    def decode_cursor(
        value: str,
    ) -> tuple[str, int]:
        raw = base64.urlsafe_b64decode(
            value
            + "="
            * (-len(value) % 4)
        )

        payload = json.loads(raw)

        return (
            str(payload["ranking_id"]),
            int(payload["offset"]),
        )

    def build_ranking(
        self,
        query: str,
        mode: str,
    ) -> dict[str, Any]:
        key = self.ranking_key(
            query,
            mode,
        )

        with self.lock:
            cached = self.ranking_cache.get(
                key
            )

            if cached is not None:
                self.ranking_cache.move_to_end(
                    key
                )

                cached["ranking_cache_hit"] = True
                cached["embed_ms"] = 0.0
                cached["scan_ms"] = 0.0
                cached["sort_ms"] = 0.0

                return cached

        embed_started = time.perf_counter()
        query_vector, embed_cache_hit = (
            self.embedder.embed(query)
        )
        embed_ms = (
            time.perf_counter()
            - embed_started
        ) * 1000

        scan_started = time.perf_counter()

        all_scores = []
        all_shards = []
        all_indexes = []

        with self.lock:
            shards = list(self.shards)

        for shard_id, shard in enumerate(
            shards
        ):
            indexes = shard.indexes(mode)

            if not len(indexes):
                continue

            matrix = shard.vectors[indexes]
            scores = matrix @ query_vector

            all_scores.append(
                np.asarray(
                    scores,
                    dtype=np.float32,
                )
            )

            all_shards.append(
                np.full(
                    len(indexes),
                    shard_id,
                    dtype=np.uint16,
                )
            )

            all_indexes.append(
                np.asarray(
                    indexes,
                    dtype=np.int32,
                )
            )

        if all_scores:
            scores = np.concatenate(
                all_scores
            )

            shard_ids = np.concatenate(
                all_shards
            )

            local_indexes = np.concatenate(
                all_indexes
            )
        else:
            scores = np.empty(
                0,
                dtype=np.float32,
            )

            shard_ids = np.empty(
                0,
                dtype=np.uint16,
            )

            local_indexes = np.empty(
                0,
                dtype=np.int32,
            )

        scan_ms = (
            time.perf_counter()
            - scan_started
        ) * 1000

        sort_started = time.perf_counter()

        order = np.argsort(
            -scores,
            kind="stable",
        )

        sort_ms = (
            time.perf_counter()
            - sort_started
        ) * 1000

        ranking = {
            "ranking_id":
                key[:32],
            "cache_key":
                key,
            "query":
                clean(query),
            "mode":
                normalized_mode(mode),
            "scores":
                scores[order],
            "shard_ids":
                shard_ids[order],
            "local_indexes":
                local_indexes[order],
            "ranked_count":
                int(len(order)),
            "shards":
                shards,
            "embed_ms":
                round(embed_ms, 3),
            "scan_ms":
                round(scan_ms, 3),
            "sort_ms":
                round(sort_ms, 3),
            "embed_cache_hit":
                embed_cache_hit,
            "ranking_cache_hit":
                False,
        }

        with self.lock:
            self.ranking_cache[key] = (
                ranking
            )

            self.ranking_cache.move_to_end(
                key
            )

            while (
                len(self.ranking_cache)
                > RANKING_CACHE_SIZE
            ):
                self.ranking_cache.popitem(
                    last=False
                )

        return ranking

    def media_for(
        self,
        row: dict[str, Any],
        identifier: str,
    ):
        metadata = (
            row.get("metadata")
            if isinstance(
                row.get("metadata"),
                dict,
            )
            else {}
        )

        for key in (
            "image",
            "image_url",
            "media_url",
            "thumbnail",
            "poster",
        ):
            value = clean(
                row.get(key)
                or metadata.get(key)
            )

            if value.startswith(
                ("http://", "https://")
            ):
                return {
                    "url": value,
                    "title": "",
                    "caption": "",
                    "credit": "",
                    "source_url": "",
                }

        if not self.media:
            return None

        row_terms = set(
            re.findall(
                r"[a-z0-9_-]{3,}",
                compact_blob(row),
            )
        )

        scored = []

        for media in self.media:
            score = len(
                row_terms
                & media["terms"]
            )

            scored.append(
                (
                    score,
                    media,
                )
            )

        maximum = max(
            score
            for score, _media
            in scored
        )

        tied = [
            media
            for score, media in scored
            if score == maximum
        ]

        seed = int(
            hashlib.sha256(
                identifier.encode()
            ).hexdigest()[:16],
            16,
        )

        selected = tied[
            seed % len(tied)
        ]

        return {
            "url": selected.get("url", ""),
            "title": selected.get("title", ""),
            "caption": selected.get("caption", ""),
            "credit": selected.get("credit", ""),
            "source_url": selected.get("source_url", ""),
        }

    def page(
        self,
        payload: dict[str, Any],
    ):
        started = time.perf_counter()

        query = clean(
            payload.get("query")
            or payload.get("text")
            or payload.get("q")
        )

        mode = normalized_mode(
            payload.get("mode")
            or payload.get("domain")
            or "unified"
        )

        page_size = int(
            payload.get("page_size")
            or payload.get("limit")
            or payload.get("k")
            or PAGE_SIZE
        )

        page_size = max(
            1,
            min(PAGE_SIZE, page_size),
        )

        offset = max(
            0,
            int(payload.get("offset") or 0),
        )

        ranking_id = clean(
            payload.get("ranking_id")
        )

        cursor = clean(
            payload.get("cursor")
            or payload.get("next_cursor")
        )

        if cursor:
            cursor_ranking_id, offset = (
                self.decode_cursor(cursor)
            )

            if (
                ranking_id
                and ranking_id
                != cursor_ranking_id
            ):
                raise LookupError(
                    "Cursor ranking mismatch"
                )

            ranking_id = cursor_ranking_id

        ranking = None

        if ranking_id:
            with self.lock:
                for cached in (
                    self.ranking_cache.values()
                ):
                    if (
                        cached["ranking_id"]
                        == ranking_id
                    ):
                        ranking = cached
                        break

        if ranking is None:
            if not query:
                raise LookupError(
                    "Ranking expired; repeat query"
                )

            ranking = self.build_ranking(
                query,
                mode,
            )

        ranked_count = int(
            ranking["ranked_count"]
        )

        offset = min(
            offset,
            ranked_count,
        )

        end = min(
            ranked_count,
            offset + page_size,
        )

        rows = []

        serialize_started = (
            time.perf_counter()
        )

        for position in range(
            offset,
            end,
        ):
            shard_id = int(
                ranking["shard_ids"][
                    position
                ]
            )

            local_index = int(
                ranking["local_indexes"][
                    position
                ]
            )

            shard = ranking["shards"][
                shard_id
            ]

            row = shard.metadata.read(
                local_index
            )

            identifier = stable_id(
                row,
                (
                    shard.key
                    + ":"
                    + str(local_index)
                ),
            )

            score = float(
                ranking["scores"][position]
            )

            row.update(
                {
                    "id":
                        identifier,
                    "rank":
                        position + 1,
                    "score":
                        score,
                    "resonance":
                        score,
                    "field_source":
                        shard.source,
                }
            )

            media = self.media_for(
                row,
                identifier,
            )

            if media:
                row["image"] = media["url"]
                row["image_url"] = media["url"]
                row["media_url"] = media["url"]
                row["thumbnail"] = media["url"]
                row["media"] = media

            rows.append(row)

        serialize_ms = (
            time.perf_counter()
            - serialize_started
        ) * 1000

        has_more = end < ranked_count

        next_cursor = (
            self.encode_cursor(
                ranking["ranking_id"],
                end,
            )
            if has_more
            else None
        )

        total_ms = (
            time.perf_counter()
            - started
        ) * 1000

        return {
            "ok":
                True,
            "query":
                ranking["query"],
            "mode":
                ranking["mode"],
            "dimension":
                72,
            "field_count":
                self.count,
            "ranked_count":
                ranked_count,
            "count":
                ranked_count,
            "returned":
                len(rows),
            "loaded_count":
                end,
            "page_size":
                page_size,
            "offset":
                offset,
            "has_more":
                has_more,
            "ranking_id":
                ranking["ranking_id"],
            "next_cursor":
                next_cursor,
            "cursor":
                next_cursor,
            "embed_ms":
                ranking["embed_ms"],
            "scan_ms":
                ranking["scan_ms"],
            "sort_ms":
                ranking["sort_ms"],
            "serialize_ms":
                round(
                    serialize_ms,
                    3,
                ),
            "latency_ms":
                round(total_ms, 3),
            "embed_cache_hit":
                ranking[
                    "embed_cache_hit"
                ],
            "ranking_cache_hit":
                ranking[
                    "ranking_cache_hit"
                ],
            "results":
                rows,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = (
        "SEMBIOTICFastField/1.0"
    )

    @property
    def field(self) -> FastField:
        return self.server.field

    def log_message(
        self,
        format_string,
        *args,
    ):
        print(
            "[http] "
            + format_string % args,
            flush=True,
        )

    def send_json(
        self,
        status: int,
        payload: Any,
    ):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.send_header(
            "Cache-Control",
            "no-store",
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "content-type",
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, HEAD, POST, OPTIONS",
        )
        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json(204, {})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        route = self.path.split(
            "?",
            1,
        )[0]

        if route in {
            "/field/v1/manifest",
            "/field/v1/health",
            "/manifest",
            "/health",
        }:
            self.send_json(
                200,
                self.field.manifest(),
            )
            return

        if route in {
            "/field/v1/media-manifest",
            "/media-manifest",
        }:
            self.send_json(
                200,
                self.field.media,
            )
            return

        self.send_json(
            404,
            {"error": "not found"},
        )

    def do_POST(self):
        route = self.path.split(
            "?",
            1,
        )[0]

        if route not in {
            "/field/v1/search",
            "/search",
        }:
            self.send_json(
                404,
                {"error": "not found"},
            )
            return

        try:
            size = int(
                self.headers.get(
                    "content-length"
                )
                or 0
            )

            payload = json.loads(
                self.rfile.read(size)
            )

            response = self.field.page(
                payload
            )

            self.send_json(
                200,
                response,
            )

        except LookupError as error:
            self.send_json(
                409,
                {
                    "error": str(error),
                    "retry": "repeat_query",
                },
            )

        except Exception as error:
            self.send_json(
                500,
                {
                    "error":
                        "fast field search failed",
                    "detail":
                        repr(error),
                },
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--embed-url",
        default=(
            "http://127.0.0.1:8000/v1/embed"
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8799,
    )

    args = parser.parse_args()

    field = FastField(
        Path(args.root),
        args.embed_url,
    )

    server = ThreadingHTTPServer(
        (args.host, args.port),
        Handler,
    )

    server.field = field

    print(
        f"SEMBIOTIC FAST FIELD · "
        f"{field.count:,} objects · "
        f"http://{args.host}:{args.port}",
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()

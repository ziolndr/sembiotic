#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.request

import numpy as np


PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 50
CACHE_MAX = 12
CACHE_TTL_SECONDS = 6 * 60 * 60


def excluded(path: Path) -> bool:
    blocked = {
        ".git",
        ".vercel",
        "backups",
        "node_modules",
        "__pycache__",
    }

    return any(
        part.lower() in blocked
        for part in path.parts
    )


def clean(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def normalized_mode(value: Any) -> str:
    value = clean(value).lower()

    aliases = {
        "": "unified",
        "all": "unified",
        "everything": "unified",
        "designs": "design",
        "synthetic design": "design",
        "cell": "cells",
        "pathway": "pathways",
        "image": "images",
        "assay": "assays",
        "paper": "papers",
        "product": "products",
        "experiment": "experiments",
        "operation": "operations",
    }

    return aliases.get(value, value)


def json_line_count(path: Path) -> int:
    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as handle:
        return sum(
            1
            for line in handle
            if line.strip()
        )


def nested_strings(payload: Any):
    if isinstance(payload, dict):
        for value in payload.values():
            yield from nested_strings(value)

    elif isinstance(payload, list):
        for value in payload:
            yield from nested_strings(value)

    elif isinstance(payload, str):
        yield payload


def declared_files(
    manifest_path: Path,
    manifest: dict[str, Any],
    suffixes: tuple[str, ...],
):
    seen = set()

    for value in nested_strings(manifest):
        lowered = value.lower()

        if not lowered.endswith(suffixes):
            continue

        candidate = Path(value).expanduser()

        possibilities = [
            candidate,
            manifest_path.parent / candidate,
            manifest_path.parent / candidate.name,
        ]

        for possibility in possibilities:
            try:
                resolved = possibility.resolve()
            except Exception:
                continue

            if resolved in seen:
                continue

            seen.add(resolved)

            if resolved.is_file():
                yield resolved


def record_blob(row: dict[str, Any]) -> str:
    values = []

    for key in (
        "domain",
        "mode",
        "category",
        "subcategory",
        "object_type",
        "type",
        "source",
        "name",
        "title",
        "description",
        "summary",
        "text",
    ):
        value = row.get(key)

        if value is not None:
            values.append(str(value))

    metadata = row.get("metadata")

    if isinstance(metadata, dict):
        for key in (
            "domain",
            "mode",
            "category",
            "subcategory",
            "object_type",
            "type",
            "source",
        ):
            value = metadata.get(key)

            if value is not None:
                values.append(str(value))

    return clean(" ".join(values)).lower()


MODE_TERMS = {
    "design": (
        "design",
        "protocell",
        "synthetic life",
        "synthetic biology",
    ),
    "cells": (
        "cell",
        "neuron",
        "astrocyte",
        "microglia",
        "stem cell",
        "organoid",
        "cell model",
    ),
    "pathways": (
        "pathway",
        "signaling",
        "mechanism",
        "metabolic network",
    ),
    "images": (
        "image",
        "imaging",
        "microscopy",
        "phenotype",
        "morphology",
        "spatial",
    ),
    "assays": (
        "assay",
        "qpcr",
        "panel",
        "reporter",
        "readout",
        "screen",
    ),
    "papers": (
        "paper",
        "publication",
        "article",
        "study",
        "journal",
        "literature",
    ),
    "products": (
        "product",
        "reagent",
        "vector",
        "protein",
        "kit",
        "catalog",
    ),
    "experiments": (
        "experiment",
        "validation",
        "protocol",
        "control",
        "perturbation",
        "model system",
    ),
    "operations": (
        "operation",
        "shipping",
        "cold chain",
        "inventory",
        "quality",
        "capa",
        "vendor",
        "logistics",
    ),
}


def row_matches_mode(
    row: dict[str, Any],
    mode: str,
) -> bool:
    mode = normalized_mode(mode)

    if mode == "unified":
        return True

    blob = record_blob(row)

    if mode == "design":
        source = clean(row.get("source")).lower()
        domain = clean(
            row.get("domain")
            or row.get("mode")
        ).lower()

        if (
            source == "sembiotic design field"
            or domain == "design"
        ):
            return True

    terms = MODE_TERMS.get(
        mode,
        (mode,),
    )

    return any(
        term in blob
        for term in terms
    )


def bucket_counts(
    rows: list[dict[str, Any]],
    ordered_indexes: np.ndarray,
) -> dict[str, int]:
    counts = Counter()
    counts["all"] = int(len(ordered_indexes))

    for raw_index in ordered_indexes:
        row = rows[int(raw_index)]
        blob = record_blob(row)

        for bucket, terms in MODE_TERMS.items():
            if row_matches_mode(row, bucket):
                counts[bucket] += 1

    return dict(counts)


def stable_identifier(row: dict[str, Any], index: int) -> str:
    value = (
        row.get("id")
        or row.get("code")
        or row.get("identifier")
        or row.get("doi")
        or row.get("url")
    )

    if value:
        return str(value)

    raw = (
        str(row.get("title") or row.get("name") or "")
        + "\n"
        + str(row.get("source") or "")
        + "\n"
        + str(index)
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


class FieldIndex:
    def __init__(
        self,
        root: Path,
        embed_url: str | None,
    ) -> None:
        self.root = root.resolve()
        self.started = time.time()
        self.lock = RLock()
        self.cursor_secret = secrets.token_bytes(32)
        self.cache: OrderedDict[
            str,
            dict[str, Any],
        ] = OrderedDict()

        (
            self.manifest_path,
            self.manifest,
            self.vectors_path,
            self.metadata_path,
        ) = self.discover()

        self.dimension = int(
            self.manifest.get("dimension")
            or self.manifest.get("dim")
            or 72
        )

        self.rows = self.load_rows()

        if self.vectors_path.suffix.lower() == ".npy":
            self.vectors = np.load(
                self.vectors_path,
                mmap_mode="r",
            )
        else:
            self.vectors = np.memmap(
                self.vectors_path,
                mode="r",
                dtype="<f4",
                shape=(
                    len(self.rows),
                    self.dimension,
                ),
            )

        if (
            self.vectors.ndim != 2
            or self.vectors.shape[1] != self.dimension
        ):
            raise RuntimeError(
                f"Invalid vectors shape: "
                f"{self.vectors.shape}"
            )

        if self.vectors.shape[0] != len(self.rows):
            raise RuntimeError(
                f"Vector/metadata mismatch: "
                f"{self.vectors.shape[0]} vectors vs "
                f"{len(self.rows)} rows."
            )

        self.count = len(self.rows)

        self.embedding_url = clean(
            embed_url
            or os.environ.get(
                "ARBITER_EMBED_URL"
            )
            or self.manifest.get(
                "embedding_url"
            )
            or "http://127.0.0.1:8000/v1/embed"
        )

        self.fingerprint = clean(
            self.manifest.get(
                "corpus_fingerprint"
            )
            or self.manifest.get(
                "fingerprint"
            )
        )

        if not self.fingerprint:
            fingerprint = hashlib.sha256()
            fingerprint.update(
                str(self.vectors_path.stat().st_size).encode()
            )
            fingerprint.update(
                str(self.metadata_path.stat().st_size).encode()
            )
            fingerprint.update(
                str(self.count).encode()
            )
            self.fingerprint = fingerprint.hexdigest()

        self.media_catalog = self.load_media_catalog()

    def discover(self):
        manifests = []

        for candidate_file in self.root.rglob(
            "manifest.json"
        ):
            if excluded(candidate_file):
                continue

            try:
                payload = json.loads(
                    candidate_file.read_text(
                        encoding="utf-8",
                    )
                )
            except Exception:
                continue

            dimension = int(
                payload.get("dimension")
                or payload.get("dim")
                or 0
            )

            count = int(
                payload.get("count")
                or payload.get("object_count")
                or 0
            )

            if dimension == 72 and count > 0:
                manifests.append(
                    (
                        candidate_file,
                        payload,
                    )
                )

        if not manifests:
            raise RuntimeError(
                "No ready 72D field manifest was found."
            )

        manifests.sort(
            key=lambda item: (
                item[1].get("status") == "ready",
                int(
                    item[1].get("count")
                    or item[1].get("object_count")
                    or 0
                ),
                item[0].stat().st_mtime,
            ),
            reverse=True,
        )

        manifest_path, manifest = manifests[0]

        count = int(
            manifest.get("count")
            or manifest.get("object_count")
            or 0
        )

        dimension = int(
            manifest.get("dimension")
            or manifest.get("dim")
            or 72
        )

        vector_candidates = list(
            declared_files(
                manifest_path,
                manifest,
                (
                    ".npy",
                    ".f32",
                    ".bin",
                ),
            )
        )

        for pattern in (
            "vectors.npy",
            "*.f32",
            "*vector*.bin",
            "*.npy",
        ):
            vector_candidates.extend(
                candidate_file
                for candidate_file in self.root.rglob(
                    pattern
                )
                if (
                    candidate_file.is_file()
                    and not excluded(candidate_file)
                )
            )

        seen = set()
        valid_vectors = []

        for candidate_file in vector_candidates:
            try:
                candidate_file = candidate_file.resolve()
            except Exception:
                continue

            if candidate_file in seen:
                continue

            seen.add(candidate_file)

            try:
                if candidate_file.suffix.lower() == ".npy":
                    array = np.load(
                        candidate_file,
                        mmap_mode="r",
                    )

                    valid = (
                        array.ndim == 2
                        and array.shape[1] == dimension
                    )

                    rows = (
                        int(array.shape[0])
                        if valid
                        else 0
                    )
                else:
                    size = candidate_file.stat().st_size
                    unit = dimension * 4
                    valid = (
                        size > 0
                        and size % unit == 0
                    )
                    rows = (
                        size // unit
                        if valid
                        else 0
                    )
            except Exception:
                continue

            if valid:
                valid_vectors.append(
                    (
                        candidate_file,
                        rows,
                    )
                )

        if not valid_vectors:
            raise RuntimeError(
                "No valid 72D vector file was found."
            )

        valid_vectors.sort(
            key=lambda item: (
                item[1] == count,
                item[0].parent
                == manifest_path.parent,
                item[1],
                item[0].stat().st_mtime,
            ),
            reverse=True,
        )

        vectors_path, vector_count = valid_vectors[0]

        metadata_candidates = list(
            declared_files(
                manifest_path,
                manifest,
                (
                    ".jsonl",
                    ".ndjson",
                ),
            )
        )

        for filename in (
            "metadata.jsonl",
            "objects.jsonl",
            "records.jsonl",
            "*.ndjson",
        ):
            metadata_candidates.extend(
                candidate_file
                for candidate_file in self.root.rglob(
                    filename
                )
                if (
                    candidate_file.is_file()
                    and not excluded(candidate_file)
                )
            )

        seen = set()
        valid_metadata = []

        for candidate_file in metadata_candidates:
            try:
                candidate_file = candidate_file.resolve()
            except Exception:
                continue

            if candidate_file in seen:
                continue

            seen.add(candidate_file)

            try:
                rows = json_line_count(
                    candidate_file
                )
            except Exception:
                continue

            valid_metadata.append(
                (
                    candidate_file,
                    rows,
                )
            )

        if not valid_metadata:
            raise RuntimeError(
                "No JSONL metadata file was found."
            )

        valid_metadata.sort(
            key=lambda item: (
                item[1] == vector_count,
                item[0].parent
                == vectors_path.parent,
                item[0].name
                in {
                    "metadata.jsonl",
                    "objects.jsonl",
                },
                item[1],
                item[0].stat().st_mtime,
            ),
            reverse=True,
        )

        metadata_path, metadata_count = valid_metadata[0]

        if metadata_count != vector_count:
            raise RuntimeError(
                f"Resolved metadata/vector mismatch: "
                f"{metadata_count} rows vs "
                f"{vector_count} vectors."
            )

        return (
            manifest_path,
            manifest,
            vectors_path,
            metadata_path,
        )

    def load_rows(self) -> list[dict[str, Any]]:
        rows = []

        with self.metadata_path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as handle:
            for line_number, line in enumerate(
                handle,
                1,
            ):
                line = line.strip()

                if not line:
                    continue

                try:
                    row = json.loads(line)
                except Exception as error:
                    raise RuntimeError(
                        f"Invalid metadata JSON on line "
                        f"{line_number}: {error}"
                    )

                if not isinstance(row, dict):
                    row = {
                        "text": str(row),
                    }

                rows.append(row)

        return rows

    def load_media_catalog(self):
        candidates = [
            self.root
            / "public"
            / "assets"
            / "media_catalog.json",
            self.root
            / "public"
            / "media_catalog.json",
            self.root
            / "assets"
            / "media_catalog.json",
            self.root
            / "media_catalog.json",
        ]

        candidates.extend(
            candidate_file
            for candidate_file in self.root.rglob(
                "media_catalog.json"
            )
            if not excluded(candidate_file)
        )

        for candidate_file in candidates:
            if not candidate_file.is_file():
                continue

            try:
                return json.loads(
                    candidate_file.read_text(
                        encoding="utf-8",
                    )
                )
            except Exception:
                continue

        return []

    def public_manifest(self):
        payload = dict(self.manifest)

        actual_domains = Counter(
            normalized_mode(
                row.get("domain")
                or row.get("mode")
            )
            for row in self.rows
        )

        design_count = sum(
            1
            for row in self.rows
            if row_matches_mode(
                row,
                "design",
            )
        )

        payload.update(
            {
                "status": "ready",
                "count": self.count,
                "dimension": self.dimension,
                "dim": self.dimension,
                "domains": {
                    **dict(
                        payload.get("domains")
                        or {}
                    ),
                    **dict(actual_domains),
                    "design": design_count,
                },
                "design_field": {
                    **dict(
                        payload.get(
                            "design_field"
                        )
                        or {}
                    ),
                    "status": (
                        "ready"
                        if design_count
                        else "missing"
                    ),
                    "count": design_count,
                    "domain": "design",
                },
                "pagination": {
                    "page_size": PAGE_SIZE_DEFAULT,
                    "maximum_page_size": PAGE_SIZE_MAX,
                    "ranking_limit": None,
                    "cursor": True,
                    "stable_ranking": True,
                    "same_geometry": True,
                },
                "uptime_seconds": round(
                    time.time()
                    - self.started,
                    3,
                ),
            }
        )

        return payload

    def embed(self, text: str) -> np.ndarray:
        body = json.dumps(
            {
                "texts": [text],
                "use_freq": True,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            self.embedding_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": (
                    "SEMBIOTIC-PAGED-FIELD/1.0"
                ),
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=120,
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        values = None

        if isinstance(payload, list):
            values = payload

        elif isinstance(payload, dict):
            for key in (
                "vectors",
                "embeddings",
            ):
                if isinstance(
                    payload.get(key),
                    list,
                ):
                    values = payload[key]
                    break

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
                    and isinstance(
                        data[0],
                        dict,
                    )
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

        if array.shape == (
            1,
            self.dimension,
        ):
            array = array[0]

        if array.shape != (
            self.dimension,
        ):
            raise RuntimeError(
                f"Embedding shape mismatch: "
                f"{array.shape}"
            )

        norm = float(
            np.linalg.norm(array)
        )

        if not np.isfinite(norm) or norm <= 1e-12:
            raise RuntimeError(
                "Embedding has an invalid norm."
            )

        return array / norm

    def cache_cleanup(self):
        now = time.time()

        expired = [
            cache_key
            for cache_key, ranking
            in self.cache.items()
            if (
                now
                - float(
                    ranking.get(
                        "created_at",
                        0,
                    )
                )
                > CACHE_TTL_SECONDS
            )
        ]

        for cache_key in expired:
            self.cache.pop(
                cache_key,
                None,
            )

        while len(self.cache) > CACHE_MAX:
            self.cache.popitem(
                last=False
            )

    def cache_by_ranking_id(
        self,
        ranking_id: str,
    ):
        with self.lock:
            self.cache_cleanup()

            for cache_key, ranking in list(
                self.cache.items()
            ):
                if (
                    ranking.get(
                        "ranking_id"
                    )
                    == ranking_id
                ):
                    self.cache.move_to_end(
                        cache_key
                    )
                    return ranking

        return None

    def make_ranking(
        self,
        query: str,
        mode: str,
    ):
        query = clean(query)
        mode = normalized_mode(mode)

        cache_key = hashlib.sha256(
            (
                self.fingerprint
                + "\n"
                + mode
                + "\n"
                + query
            ).encode("utf-8")
        ).hexdigest()

        ranking_id = cache_key[:32]

        with self.lock:
            self.cache_cleanup()

            existing = self.cache.get(
                cache_key
            )

            if existing is not None:
                self.cache.move_to_end(
                    cache_key
                )
                return existing

        eligible = np.asarray(
            [
                index
                for index, row
                in enumerate(self.rows)
                if row_matches_mode(
                    row,
                    mode,
                )
            ],
            dtype=np.int64,
        )

        if (
            mode != "unified"
            and len(eligible) == 0
        ):
            eligible = np.asarray(
                [],
                dtype=np.int64,
            )

        query_vector = self.embed(query)

        scores = np.empty(
            len(eligible),
            dtype=np.float32,
        )

        chunk_size = 25000

        for start in range(
            0,
            len(eligible),
            chunk_size,
        ):
            end = min(
                len(eligible),
                start + chunk_size,
            )

            selected = eligible[start:end]

            matrix = np.asarray(
                self.vectors[selected],
                dtype=np.float32,
            )

            scores[start:end] = (
                matrix @ query_vector
            )

        if len(eligible):
            order = np.lexsort(
                (
                    eligible,
                    -scores,
                )
            )

            ordered_indexes = eligible[
                order
            ]

            ordered_scores = scores[
                order
            ]
        else:
            ordered_indexes = eligible
            ordered_scores = scores

        ranking = {
            "ranking_id": ranking_id,
            "cache_key": cache_key,
            "created_at": time.time(),
            "query": query,
            "mode": mode,
            "indexes": ordered_indexes,
            "scores": ordered_scores,
            "ranked_count": int(
                len(ordered_indexes)
            ),
            "bucket_counts": bucket_counts(
                self.rows,
                ordered_indexes,
            ),
        }

        with self.lock:
            self.cache[cache_key] = ranking
            self.cache.move_to_end(
                cache_key
            )
            self.cache_cleanup()

        return ranking

    def encode_cursor(
        self,
        ranking_id: str,
        offset: int,
    ) -> str:
        raw = json.dumps(
            {
                "ranking_id": ranking_id,
                "offset": int(offset),
                "fingerprint": (
                    self.fingerprint[:16]
                ),
            },
            separators=(",", ":"),
        ).encode("utf-8")

        payload = base64.urlsafe_b64encode(
            raw
        ).decode("ascii").rstrip("=")

        signature = hmac.new(
            self.cursor_secret,
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()[:16]

        signed = base64.urlsafe_b64encode(
            signature
        ).decode("ascii").rstrip("=")

        return payload + "." + signed

    def decode_cursor(
        self,
        token: str,
    ) -> tuple[str, int]:
        try:
            payload, signed = token.split(
                ".",
                1,
            )

            expected = hmac.new(
                self.cursor_secret,
                payload.encode("ascii"),
                hashlib.sha256,
            ).digest()[:16]

            received = base64.urlsafe_b64decode(
                signed
                + "="
                * (-len(signed) % 4)
            )

            if not hmac.compare_digest(
                expected,
                received,
            ):
                raise ValueError(
                    "cursor signature mismatch"
                )

            raw = base64.urlsafe_b64decode(
                payload
                + "="
                * (-len(payload) % 4)
            )

            decoded = json.loads(
                raw.decode("utf-8")
            )

            if (
                decoded.get("fingerprint")
                != self.fingerprint[:16]
            ):
                raise ValueError(
                    "field fingerprint changed"
                )

            return (
                str(
                    decoded["ranking_id"]
                ),
                int(
                    decoded["offset"]
                ),
            )

        except Exception as error:
            raise LookupError(
                f"ranking cursor expired: "
                f"{error}"
            )

    def page(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        requested = (
            payload.get("page_size")
            or payload.get("limit")
            or payload.get("k")
            or payload.get("top_k")
            or PAGE_SIZE_DEFAULT
        )

        try:
            page_size = int(requested)
        except Exception:
            page_size = PAGE_SIZE_DEFAULT

        page_size = max(
            1,
            min(
                PAGE_SIZE_MAX,
                page_size,
            ),
        )

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

        ranking_id = clean(
            payload.get("ranking_id")
        )

        offset = max(
            0,
            int(
                payload.get("offset")
                or 0
            ),
        )

        cursor = clean(
            payload.get("cursor")
            or payload.get("next_cursor")
        )

        ranking = None

        if cursor:
            cursor_ranking_id, cursor_offset = (
                self.decode_cursor(
                    cursor
                )
            )

            if (
                ranking_id
                and ranking_id
                != cursor_ranking_id
            ):
                raise LookupError(
                    "ranking cursor does not match "
                    "the requested ranking"
                )

            ranking_id = cursor_ranking_id
            offset = cursor_offset

            ranking = self.cache_by_ranking_id(
                ranking_id
            )

        elif ranking_id:
            ranking = self.cache_by_ranking_id(
                ranking_id
            )

        if ranking is None:
            if not query:
                raise LookupError(
                    "ranking cache expired; "
                    "repeat the query"
                )

            ranking = self.make_ranking(
                query,
                mode,
            )

            if (
                ranking_id
                and ranking_id
                != ranking["ranking_id"]
            ):
                raise LookupError(
                    "ranking identifier changed"
                )

            ranking_id = ranking[
                "ranking_id"
            ]

        query = ranking["query"]
        mode = ranking["mode"]

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

        result_rows = []

        page_indexes = ranking[
            "indexes"
        ][offset:end]

        page_scores = ranking[
            "scores"
        ][offset:end]

        for page_position, (
            raw_index,
            score,
        ) in enumerate(
            zip(
                page_indexes,
                page_scores,
            ),
            start=offset + 1,
        ):
            source_index = int(
                raw_index
            )

            row = dict(
                self.rows[source_index]
            )

            row.update(
                {
                    "id": stable_identifier(
                        row,
                        source_index,
                    ),
                    "rank": page_position,
                    "score": float(score),
                    "resonance": float(score),
                }
            )

            result_rows.append(row)

        has_more = end < ranked_count

        next_cursor = (
            self.encode_cursor(
                ranking_id,
                end,
            )
            if has_more
            else None
        )

        return {
            "ok": True,
            "query": query,
            "mode": mode,
            "source": "LOCAL 72D FIELD",
            "dimension": self.dimension,
            "field_count": self.count,
            "scanned": ranked_count,
            "count": ranked_count,
            "ranked_count": ranked_count,
            "eligible_count": ranked_count,
            "returned": len(result_rows),
            "loaded_count": end,
            "page_size": page_size,
            "offset": offset,
            "next_offset": (
                end
                if has_more
                else None
            ),
            "has_more": has_more,
            "ranking_id": ranking_id,
            "next_cursor": next_cursor,
            "cursor": next_cursor,
            "field_fingerprint": (
                self.fingerprint
            ),
            "bucket_counts": ranking[
                "bucket_counts"
            ],
            "results": result_rows,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = (
        "SEMBIOTICPagedField/1.0"
    )

    @property
    def field(self) -> FieldIndex:
        return self.server.field

    def log_message(
        self,
        format_string: str,
        *args: Any,
    ) -> None:
        print(
            f"[http] {self.address_string()} · "
            f"{format_string % args}",
            flush=True,
        )

    def send_json(
        self,
        status: int,
        payload: Any,
    ) -> None:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(raw)),
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
            self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_json(
            204,
            {},
        )

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        route = self.path.split(
            "?",
            1,
        )[0]

        if route in {
            "/field/v1/manifest",
            "/manifest",
            "/v1/manifest",
            "/health",
            "/field/v1/health",
        }:
            self.send_json(
                200,
                self.field.public_manifest(),
            )
            return

        if route in {
            "/field/v1/media-manifest",
            "/media-manifest",
        }:
            self.send_json(
                200,
                self.field.media_catalog,
            )
            return

        self.send_json(
            404,
            {
                "error": "not found",
            },
        )

    def do_POST(self) -> None:
        route = self.path.split(
            "?",
            1,
        )[0]

        if route not in {
            "/field/v1/search",
            "/search",
            "/v1/search",
        }:
            self.send_json(
                404,
                {
                    "error": "not found",
                },
            )
            return

        try:
            content_length = int(
                self.headers.get(
                    "content-length"
                )
                or 0
            )
        except Exception:
            content_length = 0

        if (
            content_length <= 0
            or content_length > 2_000_000
        ):
            self.send_json(
                400,
                {
                    "error": (
                        "invalid request body"
                    ),
                },
            )
            return

        try:
            payload = json.loads(
                self.rfile.read(
                    content_length
                )
            )
        except Exception:
            self.send_json(
                400,
                {
                    "error": "invalid JSON",
                },
            )
            return

        started = time.perf_counter()

        try:
            result = self.field.page(
                payload
            )

            result["latency_ms"] = round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                3,
            )

            self.send_json(
                200,
                result,
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
                    "error": (
                        "field search failed"
                    ),
                    "detail": repr(error),
                },
            )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "location",
        nargs="?",
    )

    parser.add_argument(
        "--root",
    )

    parser.add_argument(
        "--field",
        dest="field_option",
    )

    parser.add_argument(
        "--embed-url",
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

    args, _unknown = (
        parser.parse_known_args()
    )

    project_root = Path(
        args.field_option
        or args.root
        or args.location
        or Path(__file__).resolve().parents[1]
    ).expanduser().resolve()

    field = FieldIndex(
        project_root,
        args.embed_url,
    )

    server = ThreadingHTTPServer(
        (
            args.host,
            args.port,
        ),
        Handler,
    )

    server.field = field

    print(
        f"SEMBIOTIC paged field · "
        f"{field.count:,} objects · "
        f"{field.dimension}D · "
        f"http://{args.host}:{args.port}",
        flush=True,
    )

    print(
        f"vectors:  {field.vectors_path}",
        flush=True,
    )

    print(
        f"metadata: {field.metadata_path}",
        flush=True,
    )

    print(
        f"embed:    {field.embedding_url}",
        flush=True,
    )

    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

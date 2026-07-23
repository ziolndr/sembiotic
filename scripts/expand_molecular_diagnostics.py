#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

import numpy as np


DIMENSION = 72
SHARD_SIZE = 5000

STRONG_TERMS = (
    "molecular diagnostic",
    "molecular diagnostics",
    "cell-free dna",
    "cell free dna",
    "cfdna",
    "ctdna",
    "circulating tumor dna",
    "liquid biopsy",
    "noninvasive prenatal",
    "non-invasive prenatal",
    "nipt",
    "aneuploid",
    "microdeletion",
    "fetal fraction",
    "fetal dna",
    "maternal plasma",
    "molecular counting",
    "quantitative counting template",
    "single molecule ngs",
    "single-molecule sequencing",
    "minimal residual disease",
    "genomic profiling",
    "variant detection",
    "diagnostic sequencing",
    "genetic testing",
    "clinical genomics",
    "clinvar",
    "digital pcr",
    "ddpcr",
    "qpcr",
    "fragmentomics",
    "methylation assay",
    "copy number variation",
    "copy-number variation",
)

MEDIUM_TERMS = (
    "sequencing",
    "genomic",
    "genetics",
    "genetic",
    "variant",
    "mutation",
    "biomarker",
    "diagnostic",
    "screening",
    "assay",
    "pcr",
    "prenatal",
    "pregnancy",
    "fetal",
    "chromosome",
    "aneuploidy",
    "cancer",
    "oncology",
    "tumor",
    "plasma",
    "serum",
    "blood test",
    "clinical validation",
    "analytical validation",
    "sensitivity",
    "specificity",
    "pathogenic",
    "gene panel",
    "molecular",
    "nucleic acid",
    "rna",
    "dna",
)

SOURCE_PRIORITY = (
    "openalex",
    "pubmed",
    "paper",
    "clinical",
    "patent",
    "web",
)


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def recurse_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from recurse_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from recurse_strings(child)
    elif isinstance(value, str):
        yield value


def row_text(row):
    values = []

    for key in (
        "title",
        "name",
        "label",
        "text",
        "description",
        "summary",
        "abstract",
        "content",
        "category",
        "type",
        "domain",
        "source",
        "keywords",
        "conditions",
        "genes",
    ):
        value = row.get(key)

        if isinstance(value, list):
            values.extend(
                str(item)
                for item in value
            )
        elif value is not None:
            values.append(str(value))

    metadata = row.get("metadata")

    if isinstance(metadata, dict):
        for key in (
            "title",
            "description",
            "summary",
            "abstract",
            "category",
            "type",
            "source",
            "keywords",
            "conditions",
            "genes",
        ):
            value = metadata.get(key)

            if isinstance(value, list):
                values.extend(
                    str(item)
                    for item in value
                )
            elif value is not None:
                values.append(str(value))

    return clean(" ".join(values))


def relevant(row, source):
    text = row_text(row).lower()

    if len(text) < 45:
        return False

    strong = sum(
        term in text
        for term in STRONG_TERMS
    )

    medium = sum(
        term in text
        for term in MEDIUM_TERMS
    )

    source = source.lower()

    if strong:
        return True

    if (
        any(
            token in source
            for token in SOURCE_PRIORITY
        )
        and medium >= 2
    ):
        return True

    return medium >= 4


def subdomain(text):
    value = text.lower()

    tests = (
        (
            "prenatal_cfdna",
            (
                "cfdna",
                "cell-free dna",
                "cell free dna",
                "nipt",
                "prenatal",
                "fetal fraction",
                "maternal plasma",
                "aneuploid",
                "microdeletion",
            ),
        ),
        (
            "liquid_biopsy",
            (
                "ctdna",
                "circulating tumor dna",
                "liquid biopsy",
                "minimal residual disease",
                "tumor fraction",
            ),
        ),
        (
            "variant_interpretation",
            (
                "clinvar",
                "pathogenic",
                "variant interpretation",
                "germline",
                "somatic",
            ),
        ),
        (
            "assay_measurement",
            (
                "molecular counting",
                "digital pcr",
                "ddpcr",
                "qpcr",
                "unique molecular",
                "spike-in",
                "limit of detection",
            ),
        ),
        (
            "clinical_validation",
            (
                "clinical validation",
                "analytical validation",
                "sensitivity",
                "specificity",
                "positive predictive",
            ),
        ),
    )

    for name, terms in tests:
        if any(term in value for term in terms):
            return name

    return "molecular_diagnostics"


def identifier(row, source, fallback):
    value = (
        row.get("id")
        or row.get("identifier")
        or row.get("doi")
        or row.get("pmid")
        or row.get("nct_id")
        or row.get("variation_id")
        or row.get("url")
        or row.get("source_url")
    )

    if value:
        return (
            source
            + ":"
            + str(value)
        )

    raw = (
        source
        + "\n"
        + row_text(row)
        + "\n"
        + fallback
    )

    return (
        source
        + ":"
        + hashlib.sha256(
            raw.encode()
        ).hexdigest()
    )


def compact_candidate(
    row,
    source,
    fallback,
):
    text = row_text(row)
    title = clean(
        row.get("title")
        or row.get("name")
        or row.get("label")
        or text[:140]
    )

    candidate = {
        "id":
            identifier(
                row,
                source,
                fallback,
            ),
        "title":
            title,
        "text":
            text[:7000],
        "description":
            clean(
                row.get("description")
                or row.get("summary")
                or row.get("abstract")
                or row.get("text")
            )[:5000],
        "object_type":
            clean(
                row.get("object_type")
                or row.get("type")
                or row.get("category")
                or "molecular_diagnostics_evidence"
            ),
        "domain":
            "molecular_diagnostics",
        "sembiotic_domain":
            "molecular_diagnostics",
        "subdomain":
            subdomain(text),
        "source":
            clean(
                row.get("source")
                or source
            ),
        "source_collection":
            source,
        "source_url":
            clean(
                row.get("source_url")
                or row.get("url")
                or row.get("link")
            ),
        "doi":
            clean(row.get("doi")),
        "pmid":
            clean(row.get("pmid")),
        "nct_id":
            clean(row.get("nct_id")),
        "variation_id":
            clean(row.get("variation_id")),
        "year":
            row.get("year"),
        "genes":
            row.get("genes") or [],
        "conditions":
            row.get("conditions") or [],
        "keywords":
            row.get("keywords") or [],
    }

    for key in (
        "image",
        "image_url",
        "media_url",
        "thumbnail",
    ):
        value = clean(row.get(key))

        if value:
            candidate[key] = value

    return candidate


def recursive_paths(payload):
    for value in recurse_strings(payload):
        try:
            path = Path(value).expanduser()

            if path.exists():
                yield path.resolve()
        except Exception:
            continue


def vector_rows(path):
    if path.suffix.lower() == ".npy":
        array = np.load(
            path,
            mmap_mode="r",
        )

        if (
            array.ndim != 2
            or array.shape[1] != DIMENSION
        ):
            return 0

        return int(array.shape[0])

    size = path.stat().st_size
    width = DIMENSION * 4

    if size <= 0 or size % width:
        return 0

    return size // width


def resolve_pair(manifest_path):
    payload = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    count = int(
        payload.get("count")
        or payload.get("object_count")
        or 0
    )

    dimension = int(
        payload.get("dimension")
        or payload.get("dim")
        or 0
    )

    if dimension != DIMENSION or count <= 0:
        return None

    vector_candidates = []
    metadata_candidates = []

    for path in recursive_paths(payload):
        if path.suffix.lower() in {
            ".f32",
            ".npy",
            ".bin",
        }:
            vector_candidates.append(path)

        elif path.suffix.lower() in {
            ".jsonl",
            ".ndjson",
        }:
            metadata_candidates.append(path)

    for name in (
        "vectors.f32",
        "vectors.npy",
        "embeddings.f32",
        "matrix.f32",
    ):
        path = manifest_path.parent / name

        if path.is_file():
            vector_candidates.append(path)

    for name in (
        "metadata.jsonl",
        "objects.jsonl",
        "records.jsonl",
        "rows.jsonl",
    ):
        path = manifest_path.parent / name

        if path.is_file():
            metadata_candidates.append(path)

    vector_candidates = list(
        dict.fromkeys(vector_candidates)
    )

    metadata_candidates = list(
        dict.fromkeys(metadata_candidates)
    )

    vector_candidates = [
        path
        for path in vector_candidates
        if vector_rows(path) > 0
    ]

    if not vector_candidates or not metadata_candidates:
        return None

    vector_candidates.sort(
        key=lambda path: (
            vector_rows(path) == count,
            vector_rows(path),
        ),
        reverse=True,
    )

    vectors_path = vector_candidates[0]
    actual_count = vector_rows(
        vectors_path
    )

    metadata_candidates.sort(
        key=lambda path: (
            path.name
            == "metadata.jsonl",
            path.stat().st_size,
        ),
        reverse=True,
    )

    source = clean(
        payload.get("source")
        or payload.get("provider")
        or manifest_path.parent.parent.name
    )

    return (
        source,
        actual_count,
        vectors_path,
        metadata_candidates[0],
    )


class ShardWriter:
    def __init__(
        self,
        root,
        database,
    ):
        self.root = root
        self.database = database
        self.count = 0
        self.total_added = 0
        self.meta = None
        self.vector = None
        self.temp = None
        self.next_number = self.resolve_number()
        self.open()

    def resolve_number(self):
        numbers = []

        for path in self.root.glob(
            "shard-*"
        ):
            match = re.fullmatch(
                r"shard-(\d+)",
                path.name,
            )

            if match:
                numbers.append(
                    int(match.group(1))
                )

        return max(numbers, default=0) + 1

    def open(self):
        self.temp = (
            self.root
            / (
                f"shard-{self.next_number:06d}"
                ".tmp"
            )
        )

        if self.temp.exists():
            import shutil
            shutil.rmtree(self.temp)

        self.temp.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.meta = (
            self.temp
            / "metadata.jsonl"
        ).open(
            "w",
            encoding="utf-8",
        )

        self.vector = (
            self.temp
            / "vectors.f32"
        ).open("wb")

        self.count = 0

    def add(
        self,
        row,
        vector,
    ):
        identifier_value = row["id"]

        try:
            self.database.execute(
                "INSERT INTO ids(id) VALUES (?)",
                (identifier_value,),
            )
            self.database.commit()
        except sqlite3.IntegrityError:
            return False

        vector = np.asarray(
            vector,
            dtype="<f4",
        )

        if vector.shape != (DIMENSION,):
            raise ValueError(
                f"Vector shape {vector.shape}"
            )

        self.meta.write(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        self.vector.write(
            vector.tobytes()
        )

        self.count += 1
        self.total_added += 1

        if self.count >= SHARD_SIZE:
            self.finalize()
            self.next_number += 1
            self.open()

        return True

    def finalize(self):
        if self.meta is None:
            return

        self.meta.flush()
        self.vector.flush()
        self.meta.close()
        self.vector.close()

        if self.count <= 0:
            import shutil
            shutil.rmtree(
                self.temp,
                ignore_errors=True,
            )
            self.meta = None
            self.vector = None
            return

        manifest = {
            "status": "ready",
            "source":
                "summon_molecular_diagnostics",
            "count":
                self.count,
            "dimension":
                DIMENSION,
            "dim":
                DIMENSION,
            "vectors":
                "vectors.f32",
            "metadata":
                "metadata.jsonl",
            "created_at":
                time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
        }

        (
            self.temp
            / "manifest.json"
        ).write_text(
            json.dumps(
                manifest,
                indent=2,
            )
            + "\n"
        )

        final = (
            self.root
            / f"shard-{self.next_number:06d}"
        )

        self.temp.rename(final)

        print(
            f"published {final.name} · "
            f"{self.count:,} candidates",
            flush=True,
        )

        self.meta = None
        self.vector = None
        self.count = 0

    def close(self):
        self.finalize()


def discover_summon_roots():
    home = Path.home()
    roots = set()

    known = (
        home
        / "Library"
        / "Application Support"
        / "SUMMON",
        home
        / "Downloads"
        / "SUMMON_CONNECTOR_FARM",
        home
        / "Downloads"
        / "SUMMON_LOCAL_WORKER_FARM",
        home
        / "Downloads"
        / "SUMMON",
        home
        / "Desktop"
        / "semantic",
    )

    for path in known:
        if path.exists():
            roots.add(path.resolve())

    downloads = home / "Downloads"

    if downloads.is_dir():
        for path in downloads.glob(
            "*SUMMON*"
        ):
            if path.is_dir():
                roots.add(path.resolve())

    try:
        request = Request(
            "http://127.0.0.1:8787/field/v1/manifest",
            headers={
                "Accept": "application/json",
            },
        )

        with urlopen(
            request,
            timeout=10,
        ) as response:
            manifest = json.load(response)

        for path in recursive_paths(
            manifest
        ):
            if path.is_dir():
                roots.add(path)
            else:
                roots.add(path.parent)

    except Exception:
        pass

    try:
        process_text = subprocess.check_output(
            [
                "/bin/ps",
                "ax",
                "-ww",
                "-o",
                "command=",
            ],
            text=True,
        )

        for match in re.findall(
            r"(/[^\s\"']+)",
            process_text,
        ):
            path = Path(match)

            if (
                path.exists()
                and "SUMMON" in str(path).upper()
            ):
                roots.add(
                    path
                    if path.is_dir()
                    else path.parent
                )

    except Exception:
        pass

    return sorted(roots)


def manifest_candidates(
    roots,
    sembiotic_root,
):
    seen = set()
    blocked = {
        ".git",
        "backups",
        "node_modules",
        "pending",
        "__pycache__",
    }

    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            continue

        if root == sembiotic_root:
            continue

        for pattern in (
            "manifest.json",
            "*.manifest.json",
        ):
            for manifest in root.rglob(
                pattern
            ):
                try:
                    resolved = manifest.resolve()
                except Exception:
                    continue

                if resolved in seen:
                    continue

                if (
                    resolved == sembiotic_root
                    or sembiotic_root
                    in resolved.parents
                ):
                    continue

                lowered = {
                    part.lower()
                    for part in resolved.parts
                }

                if lowered & blocked:
                    continue

                try:
                    payload = json.loads(
                        resolved.read_text(
                            encoding="utf-8",
                            errors="replace",
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
                    or payload.get(
                        "object_count"
                    )
                    or 0
                )

                if (
                    dimension != DIMENSION
                    or count <= 0
                ):
                    continue

                seen.add(resolved)
                yield resolved


def load_vectors(path, count):
    if path.suffix.lower() == ".npy":
        return np.load(
            path,
            mmap_mode="r",
        )

    return np.memmap(
        path,
        mode="r",
        dtype="<f4",
        shape=(count, DIMENSION),
    )


class Embedder:
    def __init__(self, url):
        self.url = url

    @staticmethod
    def parse(payload):
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

        if array.ndim == 1:
            array = array.reshape(1, -1)

        if (
            array.ndim != 2
            or array.shape[1] != DIMENSION
        ):
            raise RuntimeError(
                f"Embedding shape {array.shape}"
            )

        norms = np.linalg.norm(
            array,
            axis=1,
            keepdims=True,
        )

        return array / np.maximum(
            norms,
            1e-12,
        )

    def embed(self, texts):
        body = json.dumps(
            {
                "texts": texts,
                "use_freq": True,
            },
            separators=(",", ":"),
        ).encode()

        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type":
                    "application/json",
                "Accept":
                    "application/json",
                "User-Agent":
                    "SEMBIOTIC-MOLDX/1.0",
            },
        )

        with urlopen(
            request,
            timeout=180,
        ) as response:
            return self.parse(
                json.load(response)
            )


def curl_bytes(url):
    result = subprocess.run(
        [
            "/usr/bin/curl",
            "-fsSL",
            "--retry",
            "3",
            "--connect-timeout",
            "15",
            "--max-time",
            "180",
            "-H",
            "Accept: application/json",
            "-A",
            (
                "SEMBIOTIC-MOLDX/1.0 "
                "joel@actualgeneralintelligence.com"
            ),
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
            or (
                "curl failed with exit code "
                + str(result.returncode)
            )
        )

    return result.stdout


def fetch_json(url):
    return json.loads(
        curl_bytes(url)
    )


def pubmed_candidates(limit):
    queries = (
        (
            '"cell free DNA"[Title/Abstract] '
            'AND (prenatal OR fetal OR aneuploidy '
            'OR microdeletion OR "fetal fraction")'
        ),
        (
            '"BillionToOne"[All Fields] OR '
            '"quantitative counting template"[All Fields] '
            'OR "single molecule NGS"[All Fields]'
        ),
        (
            '("single gene NIPT"[Title/Abstract] OR '
            '"noninvasive prenatal testing"[Title/Abstract]) '
            'AND (cystic fibrosis OR spinal muscular '
            'atrophy OR sickle cell OR thalassemia)'
        ),
        (
            '("liquid biopsy"[Title/Abstract] OR '
            'ctDNA[Title/Abstract]) AND '
            '(molecular counting OR copy number OR '
            'minimal residual disease OR genomic profiling)'
        ),
    )

    per_query = max(
        25,
        limit // len(queries),
    )

    for query in queries:
        params = urlencode(
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": per_query,
                "sort": "relevance",
                "tool": "sembiotic",
                "email":
                    "joel@actualgeneralintelligence.com",
            }
        )

        result = fetch_json(
            "https://eutils.ncbi.nlm.nih.gov/"
            "entrez/eutils/esearch.fcgi?"
            + params
        )

        ids = (
            result.get("esearchresult", {})
            .get("idlist", [])
        )

        for start in range(
            0,
            len(ids),
            100,
        ):
            batch = ids[start:start + 100]

            fetch_params = urlencode(
                {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                    "tool": "sembiotic",
                    "email":
                        "joel@actualgeneralintelligence.com",
                }
            )

            raw_xml = curl_bytes(
                "https://eutils.ncbi.nlm.nih.gov/"
                "entrez/eutils/efetch.fcgi?"
                + fetch_params
            )

            root = ElementTree.fromstring(
                raw_xml
            )

            for article in root.findall(
                ".//PubmedArticle"
            ):
                pmid = clean(
                    article.findtext(
                        ".//PMID"
                    )
                )

                title_node = article.find(
                    ".//ArticleTitle"
                )

                title = clean(
                    "".join(
                        title_node.itertext()
                    )
                    if title_node is not None
                    else ""
                )

                abstract_parts = []

                for node in article.findall(
                    ".//Abstract/AbstractText"
                ):
                    label = clean(
                        node.attrib.get("Label")
                    )

                    text = clean(
                        "".join(
                            node.itertext()
                        )
                    )

                    if text:
                        abstract_parts.append(
                            (
                                label + ": " + text
                                if label
                                else text
                            )
                        )

                abstract = clean(
                    " ".join(abstract_parts)
                )

                if not title or not abstract:
                    continue

                year = clean(
                    article.findtext(
                        ".//PubDate/Year"
                    )
                    or article.findtext(
                        ".//ArticleDate/Year"
                    )
                )

                doi = ""

                for identifier_node in article.findall(
                    ".//ArticleId"
                ):
                    if (
                        identifier_node.attrib.get(
                            "IdType"
                        )
                        == "doi"
                    ):
                        doi = clean(
                            identifier_node.text
                        )
                        break

                yield {
                    "id":
                        "pubmed:" + pmid,
                    "pmid":
                        pmid,
                    "doi":
                        doi,
                    "title":
                        title,
                    "abstract":
                        abstract,
                    "text":
                        title + ". " + abstract,
                    "source":
                        "PubMed",
                    "source_url":
                        (
                            "https://pubmed.ncbi.nlm.nih.gov/"
                            + pmid
                            + "/"
                        ),
                    "object_type":
                        "paper",
                    "year":
                        year,
                }

            time.sleep(0.34)


def clinical_trial_candidates(limit):
    queries = (
        (
            '"cell free DNA" OR cfDNA OR NIPT '
            'OR aneuploidy OR microdeletion'
        ),
        (
            '"liquid biopsy" OR ctDNA OR '
            '"minimal residual disease"'
        ),
        (
            '"molecular diagnostic" OR '
            '"genomic profiling" OR '
            '"genetic testing"'
        ),
        (
            'BillionToOne OR UNITY OR Northstar'
        ),
    )

    yielded = 0

    for query in queries:
        token = None

        while yielded < limit:
            params = {
                "query.term": query,
                "pageSize": 100,
                "format": "json",
            }

            if token:
                params["pageToken"] = token

            payload = fetch_json(
                "https://clinicaltrials.gov/"
                "api/v2/studies?"
                + urlencode(params)
            )

            for study in payload.get(
                "studies",
                [],
            ):
                protocol = study.get(
                    "protocolSection",
                    {},
                )

                identification = protocol.get(
                    "identificationModule",
                    {},
                )

                description = protocol.get(
                    "descriptionModule",
                    {},
                )

                conditions = protocol.get(
                    "conditionsModule",
                    {},
                )

                interventions = protocol.get(
                    "armsInterventionsModule",
                    {},
                )

                outcomes = protocol.get(
                    "outcomesModule",
                    {},
                )

                nct_id = clean(
                    identification.get("nctId")
                )

                title = clean(
                    identification.get(
                        "briefTitle"
                    )
                    or identification.get(
                        "officialTitle"
                    )
                )

                summary = clean(
                    description.get(
                        "briefSummary"
                    )
                )

                detail = clean(
                    description.get(
                        "detailedDescription"
                    )
                )

                condition_values = (
                    conditions.get(
                        "conditions"
                    )
                    or []
                )

                intervention_values = [
                    clean(
                        intervention.get("name")
                    )
                    for intervention
                    in interventions.get(
                        "interventions",
                        [],
                    )
                ]

                outcome_values = [
                    clean(
                        outcome.get("measure")
                    )
                    for outcome
                    in outcomes.get(
                        "primaryOutcomes",
                        [],
                    )
                ]

                text = clean(
                    " ".join(
                        [
                            title,
                            summary,
                            detail,
                            "Conditions: "
                            + "; ".join(
                                condition_values
                            ),
                            "Interventions: "
                            + "; ".join(
                                intervention_values
                            ),
                            "Primary outcomes: "
                            + "; ".join(
                                outcome_values
                            ),
                        ]
                    )
                )

                if nct_id and len(text) > 80:
                    yield {
                        "id":
                            "clinicaltrials:"
                            + nct_id,
                        "nct_id":
                            nct_id,
                        "title":
                            title,
                        "text":
                            text,
                        "description":
                            summary or detail,
                        "conditions":
                            condition_values,
                        "source":
                            "ClinicalTrials.gov",
                        "source_url":
                            (
                                "https://clinicaltrials.gov/"
                                "study/"
                                + nct_id
                            ),
                        "object_type":
                            "clinical_trial",
                    }

                    yielded += 1

                    if yielded >= limit:
                        return

            token = payload.get(
                "nextPageToken"
            )

            if not token:
                break

            time.sleep(0.2)


def clinvar_candidates(limit):
    query = (
        '(pathogenic[Clinical significance] OR '
        '"likely pathogenic"[Clinical significance]) '
        'AND (CFTR[gene] OR SMN1[gene] OR '
        'HBB[gene] OR HBA1[gene] OR HBA2[gene] '
        'OR BRCA1[gene] OR BRCA2[gene] '
        'OR EGFR[gene] OR KRAS[gene])'
    )

    search = fetch_json(
        "https://eutils.ncbi.nlm.nih.gov/"
        "entrez/eutils/esearch.fcgi?"
        + urlencode(
            {
                "db": "clinvar",
                "term": query,
                "retmode": "json",
                "retmax": limit,
                "tool": "sembiotic",
                "email":
                    "joel@actualgeneralintelligence.com",
            }
        )
    )

    ids = (
        search.get("esearchresult", {})
        .get("idlist", [])
    )

    for start in range(
        0,
        len(ids),
        100,
    ):
        batch = ids[start:start + 100]

        payload = fetch_json(
            "https://eutils.ncbi.nlm.nih.gov/"
            "entrez/eutils/esummary.fcgi?"
            + urlencode(
                {
                    "db": "clinvar",
                    "id": ",".join(batch),
                    "retmode": "json",
                    "tool": "sembiotic",
                    "email":
                        "joel@actualgeneralintelligence.com",
                }
            )
        )

        result = payload.get(
            "result",
            {},
        )

        for uid in result.get(
            "uids",
            [],
        ):
            row = result.get(uid) or {}
            title = clean(row.get("title"))
            genes = row.get("genes") or []
            traits = row.get("trait_set") or []

            text = clean(
                title
                + " Genes: "
                + json.dumps(
                    genes,
                    ensure_ascii=False,
                )
                + " Traits: "
                + json.dumps(
                    traits,
                    ensure_ascii=False,
                )
                + " Classification: "
                + json.dumps(
                    row.get(
                        "germline_classification"
                    )
                    or row.get(
                        "clinical_significance"
                    )
                    or {},
                    ensure_ascii=False,
                )
            )

            if title:
                yield {
                    "id":
                        "clinvar:" + str(uid),
                    "variation_id":
                        str(uid),
                    "title":
                        title,
                    "text":
                        text,
                    "genes":
                        genes,
                    "conditions":
                        traits,
                    "source":
                        "ClinVar",
                    "source_url":
                        (
                            "https://www.ncbi.nlm.nih.gov/"
                            "clinvar/variation/"
                            + str(uid)
                            + "/"
                        ),
                    "object_type":
                        "variant",
                }

        time.sleep(0.34)


def openfda_candidates(limit):
    searches = (
        'device_name:"molecular diagnostic"',
        'device_name:"genetic test"',
        'device_name:"sequencing"',
        'device_name:"PCR"',
        'statement_or_summary:"prenatal"',
        'statement_or_summary:"liquid biopsy"',
    )

    yielded = 0

    for search in searches:
        skip = 0

        while yielded < limit:
            request_limit = min(
                100,
                limit - yielded,
            )

            url = (
                "https://api.fda.gov/"
                "device/510k.json?"
                + urlencode(
                    {
                        "search": search,
                        "limit": request_limit,
                        "skip": skip,
                    }
                )
            )

            try:
                payload = fetch_json(url)
            except Exception:
                break

            rows = payload.get(
                "results",
                [],
            )

            if not rows:
                break

            for row in rows:
                k_number = clean(
                    row.get("k_number")
                )

                title = clean(
                    row.get("device_name")
                )

                text = clean(
                    " ".join(
                        [
                            title,
                            "Applicant: "
                            + clean(
                                row.get("applicant")
                            ),
                            "Decision: "
                            + clean(
                                row.get(
                                    "decision_description"
                                )
                            ),
                            "Statement or summary: "
                            + clean(
                                row.get(
                                    "statement_or_summary"
                                )
                            ),
                            "Product code: "
                            + clean(
                                row.get(
                                    "product_code"
                                )
                            ),
                        ]
                    )
                )

                if k_number and title:
                    yield {
                        "id":
                            "openfda510k:"
                            + k_number,
                        "title":
                            title,
                        "text":
                            text,
                        "source":
                            "FDA 510(k)",
                        "source_url":
                            (
                                "https://www.accessdata.fda.gov/"
                                "scripts/cdrh/cfdocs/"
                                "cfpmn/pmn.cfm?id="
                                + k_number
                            ),
                        "object_type":
                            "diagnostic_device",
                    }

                    yielded += 1

                    if yielded >= limit:
                        return

            skip += len(rows)

            if len(rows) < request_limit:
                break

            time.sleep(0.25)


def add_public_records(
    writer,
    embedder,
    records,
):
    pending = []

    def flush():
        if not pending:
            return

        texts = [
            row["text"]
            for row in pending
        ]

        try:
            vectors = embedder.embed(
                texts
            )
        except Exception:
            if len(pending) == 1:
                print(
                    "public embedding skipped · "
                    + pending[0]["title"][:100],
                    flush=True,
                )
                pending.clear()
                return

            midpoint = len(pending) // 2
            first = pending[:midpoint]
            second = pending[midpoint:]
            pending.clear()

            add_public_records(
                writer,
                embedder,
                iter(first),
            )

            add_public_records(
                writer,
                embedder,
                iter(second),
            )
            return

        for row, vector in zip(
            pending,
            vectors,
        ):
            writer.add(
                row,
                vector,
            )

        pending.clear()

    for raw in records:
        candidate = compact_candidate(
            raw,
            clean(
                raw.get("source")
                or "public"
            ).lower(),
            clean(raw.get("id")),
        )

        if len(candidate["text"]) < 45:
            continue

        pending.append(candidate)

        if len(pending) >= 64:
            flush()

    flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        required=True,
    )
    parser.add_argument(
        "--target",
        type=int,
        default=300000,
    )
    parser.add_argument(
        "--public-seed",
        type=int,
        default=1200,
    )
    parser.add_argument(
        "--embed-url",
        default=(
            "http://127.0.0.1:8000/v1/embed"
        ),
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    expansion = (
        root
        / "field_expansion"
        / "molecular_diagnostics"
    )
    shards = expansion / "shards"
    shards.mkdir(
        parents=True,
        exist_ok=True,
    )

    database = sqlite3.connect(
        expansion / "state.sqlite"
    )

    database.execute(
        "CREATE TABLE IF NOT EXISTS ids "
        "(id TEXT PRIMARY KEY)"
    )

    database.execute(
        "CREATE TABLE IF NOT EXISTS processed "
        "(manifest TEXT PRIMARY KEY)"
    )

    database.commit()

    existing = int(
        database.execute(
            "SELECT COUNT(*) FROM ids"
        ).fetchone()[0]
    )

    print(
        f"existing molecular-diagnostics expansion: "
        f"{existing:,}",
        flush=True,
    )

    writer = ShardWriter(
        shards,
        database,
    )

    roots = discover_summon_roots()

    print(
        "SUMMON roots:",
        flush=True,
    )

    for path in roots:
        print(
            "  " + str(path),
            flush=True,
        )

    scanned_rows = 0
    matched_rows = existing
    manifests_processed = 0

    for manifest_path in manifest_candidates(
        roots,
        root,
    ):
        if matched_rows >= args.target:
            break

        processed = database.execute(
            "SELECT 1 FROM processed "
            "WHERE manifest=?",
            (str(manifest_path),),
        ).fetchone()

        if processed:
            continue

        pair = resolve_pair(
            manifest_path
        )

        if pair is None:
            database.execute(
                "INSERT OR IGNORE INTO processed "
                "(manifest) VALUES (?)",
                (str(manifest_path),),
            )
            database.commit()
            continue

        (
            source,
            count,
            vectors_path,
            metadata_path,
        ) = pair

        try:
            vectors = load_vectors(
                vectors_path,
                count,
            )

            completed = True

            with metadata_path.open(
                "r",
                encoding="utf-8",
                errors="replace",
            ) as handle:
                for index, line in enumerate(
                    handle
                ):
                    if index >= count:
                        break

                    scanned_rows += 1

                    try:
                        row = json.loads(line)
                    except Exception:
                        continue

                    if not isinstance(row, dict):
                        row = {
                            "text": str(row)
                        }

                    if not relevant(
                        row,
                        source,
                    ):
                        continue

                    candidate = compact_candidate(
                        row,
                        source,
                        (
                            str(manifest_path)
                            + ":"
                            + str(index)
                        ),
                    )

                    if writer.add(
                        candidate,
                        vectors[index],
                    ):
                        matched_rows += 1

                    if (
                        matched_rows
                        >= args.target
                    ):
                        completed = False
                        break

                    if (
                        scanned_rows
                        % 100000
                        == 0
                    ):
                        print(
                            f"scanned "
                            f"{scanned_rows:,} SUMMON rows · "
                            f"selected "
                            f"{matched_rows:,}",
                            flush=True,
                        )

            if completed:
                database.execute(
                    "INSERT OR IGNORE INTO processed "
                    "(manifest) VALUES (?)",
                    (str(manifest_path),),
                )

                database.commit()
                manifests_processed += 1

        except Exception as error:
            print(
                f"SUMMON shard skipped · "
                f"{manifest_path} · {error}",
                flush=True,
            )

    public_each = max(
        50,
        args.public_seed // 4,
    )

    embedder = Embedder(
        args.embed_url
    )

    public_sources = (
        (
            "PubMed",
            lambda: pubmed_candidates(
                public_each
            ),
        ),
        (
            "ClinicalTrials.gov",
            lambda: clinical_trial_candidates(
                public_each
            ),
        ),
        (
            "ClinVar",
            lambda: clinvar_candidates(
                public_each
            ),
        ),
        (
            "FDA 510(k)",
            lambda: openfda_candidates(
                public_each
            ),
        ),
    )

    for name, factory in public_sources:
        try:
            before = writer.total_added

            add_public_records(
                writer,
                embedder,
                factory(),
            )

            added = (
                writer.total_added
                - before
            )

            print(
                f"{name}: {added:,} new candidates",
                flush=True,
            )

        except Exception as error:
            print(
                f"{name}: skipped · {error}",
                flush=True,
            )

    writer.close()

    total = int(
        database.execute(
            "SELECT COUNT(*) FROM ids"
        ).fetchone()[0]
    )

    state = {
        "status":
            (
                "target_reached"
                if total >= args.target
                else "building"
            ),
        "count":
            total,
        "target":
            args.target,
        "summon_rows_scanned":
            scanned_rows,
        "summon_manifests_processed":
            manifests_processed,
        "updated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
    }

    (
        expansion
        / "state.json"
    ).write_text(
        json.dumps(
            state,
            indent=2,
        )
        + "\n"
    )

    print(
        f"molecular-diagnostics expansion: "
        f"{total:,}/{args.target:,}",
        flush=True,
    )


if __name__ == "__main__":
    main()

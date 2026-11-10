"""Build + upload the course vector index (Cohere embed-v4.0 → Qdrant Cloud).

Two steps, both idempotent:

1. **embed** — embed every catalog module with Cohere (``input_type=search_document``)
   into ``app/data/course_vectors.json``. Only modules whose text changed (content
   hash) are re-embedded, 96 per API call, so a full rebuild of the catalog costs a
   couple of calls against the 1,000-call/month trial quota and a no-op rerun costs 0.
2. **upload** — (re)create the Qdrant collection and upsert every vector from the
   committed file. Costs no Cohere calls, so if the free cluster is ever deleted for
   inactivity this restores it in seconds.

Usage (secrets via Infisical, never printed):
    infisical run --env dev -- uv run python scripts/reindex_vectors.py            # both
    infisical run --env dev -- uv run python scripts/reindex_vectors.py --upload-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.grounding import GroundingDoc, get_grounding  # noqa: E402
from app.agent.grounding_vector import cohere_embed, point_id  # noqa: E402
from app.config import VectorSearchConfig, get_settings  # noqa: E402

VECTORS_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "course_vectors.json"
_BATCH = 96  # Cohere's per-call text limit
_UPSERT_BATCH = 64


def _doc_text(doc: GroundingDoc) -> str:
    return f"{doc.course_title} — {doc.title}\n{doc.snippet}"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load() -> dict[str, object]:
    if VECTORS_PATH.exists():
        data: dict[str, object] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        return data
    return {}


def embed(cfg: VectorSearchConfig) -> dict[str, object]:
    docs = get_grounding()._docs()
    existing = _load()
    same_model = (
        existing.get("model") == cfg.embed_model
        and existing.get("dimensions") == cfg.embed_dimensions
    )
    old_points = {p["ref"]: p for p in existing.get("points", [])} if same_model else {}  # type: ignore[union-attr,index]

    points: list[dict[str, object]] = []
    todo: list[tuple[GroundingDoc, str]] = []
    for doc in docs:
        text = _doc_text(doc)
        h = _hash(text)
        prior = old_points.get(doc.ref)
        if prior and prior.get("hash") == h:
            points.append(prior)
        else:
            todo.append((doc, h))

    calls = 0
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(todo), _BATCH):
            batch = todo[i : i + _BATCH]
            vectors = cohere_embed(
                [_doc_text(d) for d, _ in batch],
                cfg=cfg,
                input_type="search_document",
                timeout=60,
                client=client,
            )
            calls += 1
            for (doc, h), vector in zip(batch, vectors, strict=True):
                points.append(
                    {
                        "ref": doc.ref,
                        "hash": h,
                        "course_id": doc.course_id,
                        "title": f"{doc.course_title}: {doc.title}",
                        "snippet": doc.snippet,
                        "vector": [round(x, 6) for x in vector],
                    }
                )

    points.sort(key=lambda p: str(p["ref"]))
    data = {"model": cfg.embed_model, "dimensions": cfg.embed_dimensions, "points": points}
    VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VECTORS_PATH.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"embed: {len(points)} modules, {len(todo)} re-embedded in {calls} Cohere call(s)")
    return data


def upload(cfg: VectorSearchConfig, data: dict[str, object]) -> None:
    points = data.get("points") or []
    assert isinstance(points, list) and points, "no vectors — run the embed step first"
    base = f"{cfg.qdrant_url}/collections/{cfg.collection}"
    headers = {"api-key": cfg.qdrant_api_key}
    with httpx.Client(timeout=60, headers=headers) as client:
        if client.get(base).status_code == 200:
            client.delete(base).raise_for_status()
        client.put(
            base, json={"vectors": {"size": data["dimensions"], "distance": "Cosine"}}
        ).raise_for_status()
        client.put(
            f"{base}/index",
            json={"field_name": "course_id", "field_schema": "keyword"},
        ).raise_for_status()
        for i in range(0, len(points), _UPSERT_BATCH):
            batch = points[i : i + _UPSERT_BATCH]
            client.put(
                f"{base}/points",
                params={"wait": "true"},
                json={
                    "points": [
                        {
                            "id": point_id(str(p["ref"])),
                            "vector": p["vector"],
                            "payload": {k: v for k, v in p.items() if k != "vector"},
                        }
                        for p in batch
                    ]
                },
            ).raise_for_status()
        count = client.post(f"{base}/points/count", json={"exact": True}).json()["result"]
    print(f"upload: collection '{cfg.collection}' now holds {count['count']} points")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upload-only", action="store_true", help="skip Cohere; upload file")
    parser.add_argument("--embed-only", action="store_true", help="skip the Qdrant upload")
    args = parser.parse_args()
    cfg = get_settings().require_vector_search()
    data = _load() if args.upload_only else embed(cfg)
    if not args.embed_only:
        upload(cfg, data)


if __name__ == "__main__":
    main()

"""Local hashing embedder, plus an optional OpenAI-compatible embeddings call.

The local embedder is deterministic and needs no download. It is a bag of
tokens in a fixed number of buckets, with the theme lexicon mixed in. It is
not a neural semantic model. Search never compares two different spaces.
"""

from __future__ import annotations

import hashlib
import math

from hinga.textutil import expand_themes, tokenize

DIM = 256


def _l2(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def local_embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    for token in tokenize(expand_themes(text)):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "little") % DIM
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    return _l2(vector)


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))


def openai_embed(text: str, *, base_url: str, api_key: str, model: str) -> list[float]:
    import httpx

    url = base_url.rstrip("/") + "/embeddings"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": text},
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    vector = payload["data"][0]["embedding"]
    if not isinstance(vector, list) or not vector:
        raise ValueError("embedding response was empty")
    return [float(item) for item in vector]

"""Cluster articles by embedding similarity. Global grouping, same for all users."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config
from app.db import articles as db_articles
from app.db import clusters as db_clusters
from app.llm.embeddings import EmbeddingProviderError, get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class ClusterReport:
    """Summary of a cluster run."""

    articles_embedded: int
    articles_clustered: int
    clusters_created: int


def _embedding_from_article(article: dict[str, Any]) -> list[float] | None:
    """Extract embedding from article. Returns None if invalid."""
    emb = article.get("embedding")
    if emb is None:
        return None
    if isinstance(emb, list):
        return emb
    if isinstance(emb, str):
        try:
            return json.loads(emb)
        except json.JSONDecodeError:
            return None
    return None


def _text_to_embed(article: dict[str, Any]) -> str:
    """Build text for embedding: title + content excerpt."""
    title = (article.get("title") or "").strip()
    full = (article.get("full_text") or "").strip()
    raw = (article.get("raw_text") or "").strip()
    content = full or raw
    content = content[:2000] if content else ""
    return f"{title} {content}".strip() or ""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class UnionFind:
    """Union-Find for merging clusters."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py


def _cluster_articles(
    articles: list[dict[str, Any]],
    threshold: float,
) -> list[list[str]]:
    """Group articles by embedding similarity. Returns list of clusters (each = list of article_ids)."""
    if not articles:
        return []
    n = len(articles)
    uf = UnionFind(n)
    ids = [a["id"] for a in articles]
    embeddings = [_embedding_from_article(a) for a in articles]
    for i in range(n):
        if embeddings[i] is None:
            continue
        for j in range(i + 1, n):
            if embeddings[j] is None:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                uf.union(i, j)
    groups: dict[int, list[str]] = {}
    for i in range(n):
        root = uf.find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(ids[i])
    return list(groups.values())


def run_cluster_and_embed(config: dict[str, Any] | None = None) -> ClusterReport:
    """Embed articles without embeddings, then cluster unclustered articles, create clusters."""
    cfg = config or load_config()
    processing = cfg.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    threshold = processing.get("cluster_similarity_threshold", 0.82)
    embed_limit = processing.get("embed_batch_size", 50)

    # Use 168h (1 week) when window_hours=0 to avoid clustering all articles ever
    effective_hours = window_hours if window_hours else 168
    since = datetime.now(UTC) - timedelta(hours=effective_hours)
    report = ClusterReport(articles_embedded=0, articles_clustered=0, clusters_created=0)

    # 1. Embed articles without embeddings
    has_embedding_provider = True
    try:
        provider = get_embedding_provider(cfg)
    except EmbeddingProviderError as e:
        logger.warning("Embedding provider unavailable: %s. Using singleton clusters.", e)
        has_embedding_provider = False
    else:
        to_embed = db_articles.get_recent_articles_without_embedding(since, limit=embed_limit)
        for article in to_embed:
            text = _text_to_embed(article)
            if not text:
                continue
            try:
                embedding = provider.embed(text)
                db_articles.update_article_embedding(article["id"], embedding)
                report.articles_embedded += 1
            except EmbeddingProviderError as e:
                logger.warning("Embed failed for article %s: %s", article["id"], e)

    # 2. Get articles not yet in a cluster
    if has_embedding_provider:
        to_cluster = db_articles.get_articles_with_embedding_not_in_cluster(since)
    else:
        to_cluster = db_articles.get_articles_not_in_cluster(since)
    if not to_cluster:
        return report

    report.articles_clustered = len(to_cluster)

    # 3. Cluster by similarity (or singleton if no embeddings)
    clusters = _cluster_articles(to_cluster, threshold) if to_cluster else []

    # 4. Create cluster records
    for article_ids in clusters:
        db_clusters.insert_cluster(article_ids)
        report.clusters_created += 1

    return report

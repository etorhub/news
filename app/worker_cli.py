"""Standalone CLI for pipeline processing. Run in worker container: python -m app.worker_cli <cmd>."""

import os

import click

from app.cli import run_seed_sources
from app.config import load_config
from app.db import sources as sources_db


@click.group()
def worker_cli() -> None:
    """Pipeline processing commands. Run in worker container only."""


@worker_cli.command("validate-feeds")
def validate_feeds_cmd() -> None:
    """Fetch each active feed, verify it parses, and report status."""
    from app.discovery.feed_detection import validate_feed

    feeds = sources_db.get_all_active_feeds()
    if not feeds:
        click.echo("No active feeds found. Run flask seed-sources first.")
        return

    ok_count = 0
    for feed in feeds:
        result = validate_feed(feed["feed_url"])
        status = "OK" if result["ok"] else f"FAIL: {result.get('error', 'unknown')}"
        if result["ok"]:
            ok_count += 1
        click.echo(f"  {feed['name']} ({feed.get('feed_label', 'main')}): {status}")
        if result["ok"]:
            c = result["completeness_pct"]
            click.echo(f"    items={result['item_count']} completeness={c}%")

    failed = len(feeds) - ok_count
    click.echo(f"Validated {len(feeds)} feeds: {ok_count} OK, {failed} failed.")


@worker_cli.command("score-sources")
def score_sources_cmd() -> None:
    """Compute quality scores for all sources and update the database."""
    from app.discovery.feed_detection import validate_feed
    from app.discovery.scoring import calculate_quality_score
    from app.discovery.validation import check_https

    sources = sources_db.get_all_sources()
    if not sources:
        click.echo("No sources found. Run flask seed-sources first.")
        return

    for source in sources:
        feeds = sources_db.get_feeds_for_source(source["id"])
        if not feeds:
            score = 0.0
        else:
            completeness = 0.0
            articles_total = 0.0
            feed_type = "rss"
            for f in feeds:
                result = validate_feed(f["feed_url"])
                if result["ok"]:
                    cp = result.get("completeness_pct")
                    if cp is not None:
                        completeness = max(completeness, float(cp))
                    ic = result.get("item_count")
                    if ic is not None:
                        articles_total += int(ic)
                    ft = result.get("feed_type")
                    feed_type = ft if isinstance(ft, str) else "rss"
            articles_per_day = articles_total / len(feeds) if feeds else 0.0
            https_ok = check_https(source["domain"])
            score = calculate_quality_score(
                feed_completeness_pct=completeness,
                feed_type=feed_type,
                articles_per_day=articles_per_day,
                https_ok=https_ok,
            )
        sources_db.update_source_score(source["id"], score)
        click.echo(f"  {source['name']}: score={score}")

    click.echo(f"Scored {len(sources)} sources.")


@worker_cli.command("fetch-feeds")
def fetch_feeds_cmd() -> None:
    """Run the feed fetcher once (fetch all due feeds)."""
    from app.feed.orchestrator import fetch_all_due_feeds

    config = load_config()
    report = fetch_all_due_feeds(config)
    click.echo(
        f"Fetched: checked={report.feeds_checked} "
        f"fetched={report.feeds_fetched} "
        f"inserted={report.articles_inserted} "
        f"deactivated={report.feeds_deactivated}"
    )


@worker_cli.command("enrich-articles")
def enrich_articles_cmd() -> None:
    """Extract full article content for pending articles (enrichment job)."""
    from app.extraction.extractor import enrich_articles

    config = load_config()
    report = enrich_articles(config)
    click.echo(
        f"Enrichment: checked={report.articles_checked} "
        f"extracted={report.articles_extracted} "
        f"failed={report.articles_failed} "
        f"skipped={report.articles_skipped}"
    )


@worker_cli.command("cluster-articles")
def cluster_articles_cmd() -> None:
    """Embed and cluster today's articles (cluster job)."""
    from app.clustering.service import run_cluster_and_embed

    config = load_config()
    report = run_cluster_and_embed(config)
    click.echo(
        f"Cluster: embedded={report.articles_embedded} "
        f"clustered={report.articles_clustered} "
        f"clusters_created={report.clusters_created}"
    )


@worker_cli.command("rewrite-articles")
def rewrite_articles_cmd() -> None:
    """Rewrite today's articles for all user profiles (rewrite job)."""
    from app.services.rewrite_service import run_rewrite_batch

    config = load_config()
    try:
        report = run_rewrite_batch(config)
    except Exception as e:
        click.echo(f"Rewrite job failed: {e}", err=True)
        raise SystemExit(1)
    click.echo(
        f"Rewrite: profiles={report.profiles_processed} "
        f"clusters_attempted={report.clusters_attempted} "
        f"ok={report.clusters_succeeded} "
        f"failed={report.clusters_failed}"
    )


@worker_cli.command("run-pipeline")
@click.option(
    "--sources-path",
    type=click.Path(exists=True),
    default=None,
    help="Path to sources.yaml for seed step (default: config/sources.yaml)",
)
def run_pipeline_cmd(sources_path: str | None) -> None:
    """Run the full pipeline once: seed → fetch → enrich → cluster → rewrite."""
    from app.clustering.service import run_cluster_and_embed
    from app.extraction.extractor import enrich_articles
    from app.feed.orchestrator import fetch_all_due_feeds
    from app.services.rewrite_service import run_rewrite_batch

    config = load_config()
    click.echo("Running seed-sources...")
    run_seed_sources(sources_path)
    click.echo("Running fetch...")
    r1 = fetch_all_due_feeds(config)
    click.echo(
        f"  checked={r1.feeds_checked} fetched={r1.feeds_fetched} inserted={r1.articles_inserted}"
    )

    click.echo("Running enrichment...")
    r2 = enrich_articles(config)
    click.echo(
        f"  checked={r2.articles_checked} extracted={r2.articles_extracted}"
    )

    click.echo("Running cluster...")
    r3 = run_cluster_and_embed(config)
    click.echo(
        f"  embedded={r3.articles_embedded} clustered={r3.articles_clustered} clusters={r3.clusters_created}"
    )

    click.echo("Running rewrite...")
    try:
        r4 = run_rewrite_batch(config)
    except Exception as e:
        click.echo(f"Rewrite failed: {e}", err=True)
        raise SystemExit(1)
    click.echo(
        f"  profiles={r4.profiles_processed} clusters_attempted={r4.clusters_attempted} ok={r4.clusters_succeeded} failed={r4.clusters_failed}"
    )

    click.echo("Pipeline complete.")


def main() -> None:
    """Entry point for python -m app.worker_cli."""
    if os.path.exists(".env"):
        from dotenv import load_dotenv

        load_dotenv()
    worker_cli()


if __name__ == "__main__":
    main()

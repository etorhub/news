"""Flask CLI commands for news source discovery and feed fetching."""

import click

from app.config import load_config, load_sources
from app.db import sources as sources_db
from app.discovery.feed_detection import validate_feed
from app.discovery.scoring import calculate_quality_score
from app.discovery.validation import check_https


@click.command("seed-sources")
@click.option(
    "--sources-path",
    type=click.Path(exists=True),
    default=None,
    help="Path to sources.yaml (default: config/sources.yaml)",
)
def seed_sources(sources_path: str | None) -> None:
    """Load config/sources.yaml into news_sources and source_feeds tables."""
    sources = load_sources(sources_path)
    if not sources:
        click.echo("No sources found in YAML.")
        return

    for s in sources:
        source_row = {
            "id": s["id"],
            "domain": s["domain"],
            "name": s["name"],
            "description": s.get("description"),
            "homepage_url": s["homepage_url"],
            "country_code": s["country_code"],
            "region": s.get("region"),
            "languages": s["languages"],
            "quality_score": None,
            "is_verified": False,
            "full_text_available": s.get("full_text", False),
            "status": "active",
            "last_checked_at": None,
        }
        sources_db.upsert_source(source_row)
        sources_db.delete_feeds_for_source(s["id"])
        for f in s.get("feeds", []):
            feed_row = {
                "source_id": s["id"],
                "feed_type": f.get("type", "rss"),
                "feed_url": f["url"],
                "feed_label": f.get("label"),
            }
            sources_db.insert_feed(feed_row)
        click.echo(f"  Seeded: {s['name']} ({s['id']})")

    click.echo(f"Seeded {len(sources)} sources.")


@click.command("validate-feeds")
def validate_feeds_cmd() -> None:
    """Fetch each active feed, verify it parses, and report status."""
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


@click.command("score-sources")
def score_sources_cmd() -> None:
    """Compute quality scores for all sources and update the database."""
    sources = sources_db.get_all_sources()
    if not sources:
        click.echo("No sources found. Run flask seed-sources first.")
        return

    for source in sources:
        feeds = sources_db.get_feeds_for_source(source["id"])
        if not feeds:
            score = 0.0
        else:
            # Aggregate feed metrics: use best completeness, avg articles
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
            # Rough articles/day: assume feed has ~1 day of items
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


@click.command("make-admin")
@click.argument("email", type=str)
def make_admin(email: str) -> None:
    """Grant admin privileges to a user by email."""
    from app.db import users as db_users

    user = db_users.get_user_by_email(email.strip())
    if not user:
        click.echo(f"User not found: {email}")
        raise SystemExit(1)
    db_users.set_admin(user["id"], True)
    click.echo(f"Granted admin to {email}")


@click.command("show-rewrite-failures")
@click.option("--hours", default=24, help="Look back N hours (default: 24)")
@click.option("--limit", default=50, help="Max failures to show (default: 50)")
def show_rewrite_failures(hours: int, limit: int) -> None:
    """List recent cluster rewrite failures with reasons (for diagnostics)."""
    from app.db import admin as admin_db

    failures = admin_db.get_recent_rewrite_failures(hours=hours, limit=limit)
    if not failures:
        click.echo("No rewrite failures in the last %d hours." % hours)
        return

    click.echo("Rewrite failures (last %d hours): %d" % (hours, len(failures)))
    click.echo()
    for f in failures:
        reason = f.get("error_message") or "(reason not stored — failures before error tracking)"
        created = f.get("created_at")
        ts = created.strftime("%Y-%m-%d %H:%M") if created else "—"
        click.echo("  %s  %s" % (ts, f.get("cluster_id", "?")[:8]))
        click.echo("    %s" % (reason[:100] + "…" if len(str(reason)) > 100 else reason))
        click.echo()


@click.command("fetch-feeds")
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


@click.command("enrich-articles")
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


@click.command("cluster-articles")
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


@click.command("rewrite-articles")
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


@click.command("run-pipeline")
def run_pipeline_cmd() -> None:
    """Run the full pipeline once: seed → fetch → enrich → cluster → rewrite."""
    from app.clustering.service import run_cluster_and_embed
    from app.extraction.extractor import enrich_articles
    from app.feed.orchestrator import fetch_all_due_feeds
    from app.services.rewrite_service import run_rewrite_batch

    config = load_config()
    click.echo("Running seed-sources...")
    click.get_current_context().invoke(seed_sources, sources_path=None)
    click.echo("Running fetch...")
    r1 = fetch_all_due_feeds(config)
    click.echo(f"  checked={r1.feeds_checked} fetched={r1.feeds_fetched} inserted={r1.articles_inserted}")

    click.echo("Running enrichment...")
    r2 = enrich_articles(config)
    click.echo(f"  checked={r2.articles_checked} extracted={r2.articles_extracted}")

    click.echo("Running cluster...")
    r3 = run_cluster_and_embed(config)
    click.echo(f"  embedded={r3.articles_embedded} clustered={r3.articles_clustered} clusters={r3.clusters_created}")

    click.echo("Running rewrite...")
    try:
        r4 = run_rewrite_batch(config)
    except Exception as e:
        click.echo(f"Rewrite failed: {e}", err=True)
        raise SystemExit(1)
    click.echo(f"  profiles={r4.profiles_processed} clusters_attempted={r4.clusters_attempted} ok={r4.clusters_succeeded} failed={r4.clusters_failed}")

    click.echo("Pipeline complete.")

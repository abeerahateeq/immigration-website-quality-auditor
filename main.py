"""
main.py
-------
CLI entry point. Reads a CSV of sites you are authorized to audit, runs the
scraper + LLM judgment pipeline on each, and writes Markdown + HTML reports.

Usage:
    python main.py --input sites.csv --outdir demo_output

sites.csv columns:
    url, authorized, notes
    https://example-consultancy.com, yes, "client site, permission on file"

Only rows with authorized == yes are audited. Everything else is skipped
and logged, never silently dropped.
"""
import argparse
import csv
import os
import sys
import time

from scraper import audit_site
from robots_check import is_allowed
from llm_judge import judge_site
from report_generator import generate_markdown_report, generate_html_report


def load_sites(csv_path):
    sites = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            authorized = (row.get("authorized") or "").strip().lower()
            if not url:
                continue
            sites.append({"url": url, "authorized": authorized == "yes", "notes": row.get("notes", "")})
    return sites


def run_audit(sites, delay_between_sites=1.0):
    results = []
    for entry in sites:
        url = entry["url"]

        if not entry["authorized"]:
            print(f"[SKIP] {url} -- not marked authorized=yes in sites.csv")
            continue

        print(f"[AUDIT] {url}")
        try:
            robots_ok = is_allowed(url)
            robots_status = "allowed" if robots_ok else "disallowed"
            if not robots_ok:
                print(f"  -> robots.txt disallows this bot for {url}. Skipping fetch, recording as blocked.")
                from scraper import SiteFacts
                facts = SiteFacts(url=url, reachable=False, error="robots_txt_disallowed",
                                   robots_txt_status="disallowed")
            else:
                facts = audit_site(url, robots_status=robots_status)
        except Exception as e:
            # Absolute last-resort safety net -- one bad site must never kill the batch.
            print(f"  -> UNEXPECTED ERROR, recording and continuing: {e}")
            from scraper import SiteFacts
            facts = SiteFacts(url=url, reachable=False, error=f"unexpected:{type(e).__name__}")

        if facts.reachable:
            print(f"  -> reachable, {facts.pages_crawled} page(s) crawled, requesting LLM judgment...")
            judgment = judge_site(_facts_to_plain_dict(facts))
        else:
            print(f"  -> NOT reachable ({facts.error}), skipping LLM call, recording failure.")
            judgment = {
                "score": None,
                "score_rationale": f"Site unreachable ({facts.error}); no judgment possible.",
                "missing_features": [],
                "problems": [f"Site could not be fetched: {facts.error}"],
                "recommendations": [],
                "overall_priority": "unknown",
                "_mock": False,
            }

        results.append({"facts": facts, "judgment": judgment})
        time.sleep(delay_between_sites)  # be polite between different sites too

    return results


def _facts_to_plain_dict(facts):
    from dataclasses import asdict
    return asdict(facts)


def main():
    parser = argparse.ArgumentParser(description="Audit authorized immigration consultancy websites.")
    parser.add_argument("--input", default="sites.csv", help="CSV of sites (url, authorized, notes)")
    parser.add_argument("--outdir", default="demo_output", help="Directory to write reports into")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}")
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)

    sites = load_sites(args.input)
    if not sites:
        print("No sites found in input CSV.")
        sys.exit(1)

    results = run_audit(sites)

    if not results:
        print("No authorized sites were audited (check the 'authorized' column). Nothing to report.")
        sys.exit(0)

    md = generate_markdown_report(results)
    html_report = generate_html_report(results)

    md_path = os.path.join(args.outdir, "report.md")
    html_path = os.path.join(args.outdir, "report.html")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)

    print(f"\nDone. Reports written to:\n  {md_path}\n  {html_path}")


if __name__ == "__main__":
    main()

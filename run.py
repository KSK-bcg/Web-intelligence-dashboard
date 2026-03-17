#!/usr/bin/env python3
# run.py
"""
Web Intelligence Agent — CLI Entry Point

Usage:
  python run.py --goal "Map IT division of Novartis on LinkedIn"
  python run.py --goal "Summarize https://example.com/blog"
  python run.py --list-runs
  python run.py --open <run-id>
  python run.py --setup-linkedin    # Save LinkedIn session cookies
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def cmd_run_goal(goal: str, run_id: str = None) -> None:
    from agent.orchestrator import Orchestrator
    orch = Orchestrator()
    print(f"\n🔍 Starting: {goal}\n")
    result = asyncio.run(orch.run(goal=goal, run_id_hint=run_id))
    print(f"\n✅ Done! Run ID: {result['run_id']}")
    print(f"   People found: {result['people_count']}")
    if result["changes"]:
        print(f"   Changes since last run: {len(result['changes'])}")
        for c in result["changes"]:
            if c["change_type"] == "new_hire":
                print(f"   🟢 New hire: {c['person_name']} ({c['to_value']})")
            elif c["change_type"] == "promotion":
                print(f"   🟡 Promoted: {c['person_name']} {c['from_value']} → {c['to_value']}")
            elif c["change_type"] == "departure":
                print(f"   🔴 Departed: {c['person_name']} ({c['from_value']})")
    print(f"\n📊 Report: {result['report_path']}")
    print(f"   Open with: python run.py --open {result['run_id']}\n")


def cmd_list_runs() -> None:
    from agent.store import Store
    store = Store()
    store.init_db()
    runs = store.list_runs()
    if not runs:
        print("No runs yet. Try: python run.py --goal '...'")
        return
    print(f"\n{'ID':<12} {'Status':<10} {'Target':<20} {'Goal'}")
    print("-" * 70)
    for r in runs:
        print(f"{r.id:<12} {r.status:<10} {r.target:<20} {r.goal[:40]}")
    print()


def cmd_open_report(run_id: str) -> None:
    path = Path(f"output/{run_id}/report.html")
    if not path.exists():
        print(f"❌ Report not found: {path}")
        sys.exit(1)
    abs_path = path.resolve()
    print(f"🌐 Opening: {abs_path}")
    webbrowser.open(f"file://{abs_path}")


def cmd_setup_linkedin() -> None:
    from agent.crawlers.cookie_manager import save_cookies
    print("\n🔐 LinkedIn Session Setup")
    print("=" * 40)
    print("1. Open Chrome/Safari and log into LinkedIn")
    print("2. Open DevTools (F12) → Application → Cookies → linkedin.com")
    print("3. Export cookies as JSON (use a browser extension like 'Cookie-Editor')")
    print("\nPaste your LinkedIn cookies JSON array (then press Enter twice):")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    raw = "\n".join(lines)
    try:
        cookies = json.loads(raw)
        save_cookies(cookies)
        print(f"\n✅ Saved {len(cookies)} cookies to OS keyring.")
        print("You can now run: python run.py --goal '...'")
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Web Intelligence Agent — crawl and analyze web data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --goal "Map the IT division of Roche on LinkedIn, VP level and above"
  python run.py --goal "Summarize last 10 posts at https://martinfowler.com"
  python run.py --list-runs
  python run.py --open abc12345
  python run.py --setup-linkedin
        """,
    )
    parser.add_argument("--goal", "-g", help="Natural language research goal")
    parser.add_argument("--run-id", help="Re-run with existing run ID (enables change detection)")
    parser.add_argument("--list-runs", "-l", action="store_true", help="List all prior runs")
    parser.add_argument("--open", "-o", metavar="RUN_ID", help="Open report in browser")
    parser.add_argument("--setup-linkedin", action="store_true", help="Save LinkedIn session cookies")

    args = parser.parse_args()

    if args.setup_linkedin:
        cmd_setup_linkedin()
    elif args.list_runs:
        cmd_list_runs()
    elif args.open:
        cmd_open_report(args.open)
    elif args.goal:
        cmd_run_goal(args.goal, run_id=args.run_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

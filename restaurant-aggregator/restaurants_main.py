#!/usr/bin/env python3
"""
Prague Restaurant Aggregator

Usage:
  python restaurants_main.py                  # daily incremental scan
  python restaurants_main.py --initial-scan   # one-time bulk scan of all Prague restaurants
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from restaurant_adapters import RESTAURANT_ADAPTERS
from restaurants.dedup import deduplicate
from restaurants.store import RestaurantStore


def load_config() -> dict:
    path = ROOT / "restaurants_config.yaml"
    return yaml.safe_load(path.read_text("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prague Restaurant Aggregator")
    parser.add_argument(
        "--initial-scan",
        action="store_true",
        help="Run a full bulk scan of all Prague restaurants (one-time operation)",
    )
    args = parser.parse_args()
    mode = "bulk" if args.initial_scan else "incremental"

    print(f"=== Restaurant Aggregator | mode={mode} ===")

    config = load_config()

    store_path = ROOT / config["store"]["path"]
    store = RestaurantStore(store_path)
    print(f"Loaded {len(store.all())} existing restaurants from store")

    api_keys = {
        "google_places": os.environ.get("GOOGLE_PLACES_API_KEY", ""),
        "foursquare": os.environ.get("FOURSQUARE_API_KEY", ""),
        "openstreetmap": "",
    }

    enabled_adapters = config.get("adapters", [])
    incoming: list = []

    for adapter_name in enabled_adapters:
        cls = RESTAURANT_ADAPTERS.get(adapter_name)
        if cls is None:
            print(f"[main] Unknown adapter: {adapter_name!r}, skipping")
            continue
        adapter = cls(api_key=api_keys.get(adapter_name, ""), mode=mode)
        listings = adapter._safe_fetch()
        incoming.extend(listings)

    print(f"Fetched {len(incoming)} raw listings across all sources")

    deduplicated = deduplicate(incoming)
    print(f"After deduplication: {len(deduplicated)} unique listings")

    new_listings = store.merge(deduplicated)
    print(f"New restaurants discovered: {len(new_listings)}")

    store.save()

    dashboard_cfg = config.get("dashboard", {})
    template_path = ROOT / dashboard_cfg.get("template", "docs/_restaurants_template.html")
    output_path = ROOT / dashboard_cfg.get("output", "docs/restaurants.html")

    if template_path.exists():
        output_path.write_text(template_path.read_text("utf-8"), "utf-8")
        print(f"Dashboard regenerated: {output_path}")
    else:
        print(f"[main] Dashboard template not found at {template_path}, skipping")

    print("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

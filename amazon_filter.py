#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional


NUMERIC_FIELDS = {"price", "rating", "reviews", "sales"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Amazon product list data from a CSV file."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source CSV file that contains Amazon product data.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for saving filtered results. Supports .csv and .json.",
    )
    parser.add_argument(
        "--keyword",
        help="Keep rows whose title contains the keyword (case-insensitive).",
    )
    parser.add_argument("--brand", help="Keep rows matching the specified brand.")
    parser.add_argument("--category", help="Keep rows matching the specified category.")
    parser.add_argument("--seller", help="Keep rows matching the specified seller.")
    parser.add_argument("--min-price", type=float, help="Minimum product price.")
    parser.add_argument("--max-price", type=float, help="Maximum product price.")
    parser.add_argument("--min-rating", type=float, help="Minimum product rating.")
    parser.add_argument("--min-reviews", type=int, help="Minimum review count.")
    parser.add_argument("--min-sales", type=int, help="Minimum monthly sales.")
    parser.add_argument(
        "--prime-only",
        action="store_true",
        help="Keep only products marked as Prime eligible.",
    )
    parser.add_argument(
        "--sort-by",
        choices=["price", "rating", "reviews", "sales", "title"],
        default="rating",
        help="Field used to sort results.",
    )
    parser.add_argument(
        "--descending",
        action="store_true",
        help="Sort in descending order.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to keep after filtering.",
    )
    return parser.parse_args()


def normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Optional[str]) -> Optional[int]:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def is_prime(value: Optional[str]) -> bool:
    return normalize_text(value) in {"yes", "y", "true", "1", "prime"}


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def matches(row: Dict[str, str], args: argparse.Namespace) -> bool:
    if args.keyword and args.keyword.lower() not in normalize_text(row.get("title")):
        return False

    if args.brand and normalize_text(row.get("brand")) != normalize_text(args.brand):
        return False

    if args.category and normalize_text(row.get("category")) != normalize_text(args.category):
        return False

    if args.seller and normalize_text(row.get("seller")) != normalize_text(args.seller):
        return False

    price = to_float(row.get("price"))
    if args.min_price is not None and (price is None or price < args.min_price):
        return False
    if args.max_price is not None and (price is None or price > args.max_price):
        return False

    rating = to_float(row.get("rating"))
    if args.min_rating is not None and (rating is None or rating < args.min_rating):
        return False

    reviews = to_int(row.get("reviews"))
    if args.min_reviews is not None and (reviews is None or reviews < args.min_reviews):
        return False

    sales = to_int(row.get("sales"))
    if args.min_sales is not None and (sales is None or sales < args.min_sales):
        return False

    if args.prime_only and not is_prime(row.get("is_prime")):
        return False

    return True


def sort_key(row: Dict[str, str], field: str):
    if field in NUMERIC_FIELDS:
        value = to_float(row.get(field))
        return value if value is not None else float("-inf")
    return normalize_text(row.get(field))


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)


def write_json(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def print_summary(rows: List[Dict[str, str]]) -> None:
    print(f"Matched products: {len(rows)}")
    if not rows:
        return

    for index, row in enumerate(rows[:5], start=1):
        print(
            f"{index}. {row.get('title', '')} | "
            f"brand={row.get('brand', '')} | "
            f"price={row.get('price', '')} | "
            f"rating={row.get('rating', '')} | "
            f"reviews={row.get('reviews', '')}"
        )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    rows = read_rows(input_path)

    filtered = [row for row in rows if matches(row, args)]
    filtered.sort(key=lambda row: sort_key(row, args.sort_by), reverse=args.descending)

    if args.limit is not None:
        filtered = filtered[: args.limit]

    print_summary(filtered)

    if args.output:
        output_path = Path(args.output)
        suffix = output_path.suffix.lower()
        if suffix == ".json":
            write_json(output_path, filtered)
        else:
            write_csv(output_path, filtered)
        print(f"Saved filtered results to: {output_path}")


if __name__ == "__main__":
    main()

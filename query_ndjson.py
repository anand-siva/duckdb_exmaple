#!/usr/bin/env python3

import argparse
import time

import duckdb

from seed_transactions import configure_minio


DEFAULT_INPUT = "s3://duckdb-demo/transactions-ndjson/*.ndjson"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate transaction NDJSON data directly with DuckDB."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=DEFAULT_INPUT,
        help=f"NDJSON file or glob (default: {DEFAULT_INPUT})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()

    print(f"Configuring DuckDB to read {args.input}", flush=True)
    connection = duckdb.connect(":memory:")
    try:
        configure_minio(connection)
        connection.execute("SET enable_progress_bar = true")
        connection.execute("SET progress_bar_time = 1000")
        print(
            "Scanning and parsing the NDJSON dataset. "
            "This reads every byte of all 1,000 objects...",
            flush=True,
        )
        rows = connection.execute(
            """
            SELECT
                state,
                count(*) AS transaction_count,
                sum(amount) AS total_revenue
            FROM read_ndjson(
                ?,
                columns = {
                    state: 'VARCHAR',
                    amount: 'DECIMAL(10,2)'
                }
            )
            GROUP BY state
            ORDER BY state
            """,
            [args.input],
        ).fetchall()
    finally:
        connection.close()

    total_records = sum(row[1] for row in rows)

    print("Revenue by state:")
    for state, _, total_revenue in rows:
        print(f"{state}: ${total_revenue:,.2f}")

    print()
    print("Transaction count by state:")
    for state, transaction_count, _ in rows:
        print(f"{state}: {transaction_count:,}")

    print()
    print(f"Processed {total_records:,} records in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

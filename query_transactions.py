#!/usr/bin/env python3

import argparse
import time

import duckdb

from seed_transactions import configure_minio

DEFAULT_INPUT = "s3://duckdb-demo/transactions/transactions.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query transaction Parquet data directly with DuckDB."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=DEFAULT_INPUT,
        help=f"Parquet file or glob (default: {DEFAULT_INPUT})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    started = time.perf_counter()
    connection = duckdb.connect(":memory:")
    try:
        configure_minio(connection)
        rows = connection.execute(
            """
            SELECT
                state,
                count(*) AS transaction_count,
                sum(amount) AS total_revenue
            FROM read_parquet(?)
            GROUP BY state
            ORDER BY state
            """,
            [args.input],
        ).fetchall()
    finally:
        connection.close()

    total_transactions = sum(row[1] for row in rows)

    print("Revenue and transaction count by state:")
    for state, transaction_count, total_revenue in rows:
        print(f"{state}: {transaction_count:,} transactions | ${total_revenue:,.2f}")

    elapsed = time.perf_counter() - started
    print()
    print(f"Processed {total_transactions:,} transactions in {elapsed:.2f}s")


if __name__ == "__main__":
    main()

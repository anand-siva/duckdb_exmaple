#!/usr/bin/env python3

import argparse
import time

import boto3
import duckdb
from botocore.client import Config


DEFAULT_ROWS = 1_000_000
DEFAULT_OUTPUT = "s3://duckdb-demo/transactions/transactions.parquet"
S3_ENDPOINT = "http://localhost:9000"
S3_ACCESS_KEY = "admin"
S3_SECRET_KEY = "password123"
S3_REGION = "us-east-1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic transactions and write them to Parquet with DuckDB."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help=f"number of transactions to generate (default: {DEFAULT_ROWS:,})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Parquet output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if args.rows <= 0:
        parser.error("--rows must be greater than zero")

    return args


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise SystemExit("--output must be an s3:// URI")

    bucket_and_key = uri.removeprefix("s3://").split("/", 1)
    if len(bucket_and_key) != 2 or not all(bucket_and_key):
        raise SystemExit("--output must include both a bucket and an object key")

    return bucket_and_key[0], bucket_and_key[1]


def configure_minio(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    connection.execute(
        f"""
        CREATE OR REPLACE SECRET minio (
            TYPE s3,
            KEY_ID {sql_string(S3_ACCESS_KEY)},
            SECRET {sql_string(S3_SECRET_KEY)},
            REGION {sql_string(S3_REGION)},
            ENDPOINT 'localhost:9000',
            URL_STYLE 'path',
            USE_SSL false
        )
        """
    )


def main() -> None:
    args = parse_args()
    bucket, key = parse_s3_uri(args.output)

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4"),
    )
    existing_buckets = {item["Name"] for item in s3.list_buckets()["Buckets"]}
    if bucket not in existing_buckets:
        s3.create_bucket(Bucket=bucket)

    # The output is generated data, so rerunning the seed command replaces it.
    s3.delete_object(Bucket=bucket, Key=key)

    started = time.perf_counter()
    print(f"Generating {args.rows:,} transactions with DuckDB")
    print(f"Writing {args.output}")

    connection = duckdb.connect(":memory:")
    try:
        configure_minio(connection)
        connection.execute(
            f"""
            COPY (
                SELECT
                    md5(i::VARCHAR) AS transaction_id,
                    (1 + hash(i * 17) % 10000000)::INTEGER AS customer_id,
                    list_extract(
                        ['MD', 'VA', 'PA', 'NY', 'CA', 'TX', 'FL', 'IL', 'WA', 'NC'],
                        (1 + hash(i * 23) % 10)::INTEGER
                    ) AS state,
                    list_extract(
                        ['electronics', 'clothing', 'books', 'home', 'grocery', 'sports'],
                        (1 + hash(i * 29) % 6)::INTEGER
                    ) AS product_category,
                    (5 + (hash(i * 31) % 49501) / 100.0)::DECIMAL(10, 2) AS amount,
                    TIMESTAMP '2026-01-01 00:00:00'
                        + (hash(i * 37) % 31536000) * INTERVAL '1 second' AS created_at
                FROM range({args.rows}) AS transactions(i)
            ) TO {sql_string(args.output)}
            (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
            """
        )
    finally:
        connection.close()

    elapsed = time.perf_counter() - started
    size_mib = s3.head_object(Bucket=bucket, Key=key)["ContentLength"] / (1024 * 1024)

    print(f"Seeded {args.rows:,} transactions in {elapsed:.2f}s")
    print(f"Parquet size: {size_mib:,.1f} MiB")


if __name__ == "__main__":
    main()

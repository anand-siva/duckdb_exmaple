#!/usr/bin/env python3

import argparse
import time

import boto3
import duckdb
from botocore.client import Config

from seed_transactions import (
    DEFAULT_FILES,
    DEFAULT_RECORDS_PER_FILE,
    S3_ACCESS_KEY,
    S3_ENDPOINT,
    S3_REGION,
    S3_SECRET_KEY,
    configure_minio,
    parse_s3_uri,
    sql_string,
    transaction_select,
)


DEFAULT_OUTPUT = "s3://duckdb-demo/transactions-ndjson/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic transactions and write them as NDJSON with DuckDB."
    )
    parser.add_argument(
        "--files",
        type=int,
        default=DEFAULT_FILES,
        help=f"number of NDJSON objects to create (default: {DEFAULT_FILES:,})",
    )
    parser.add_argument(
        "--records-per-file",
        type=int,
        default=DEFAULT_RECORDS_PER_FILE,
        help=f"transactions per object (default: {DEFAULT_RECORDS_PER_FILE:,})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"S3 output prefix (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if args.files <= 0:
        parser.error("--files must be greater than zero")
    if args.records_per_file <= 0:
        parser.error("--records-per-file must be greater than zero")

    return args


def main() -> None:
    args = parse_args()
    bucket, prefix = parse_s3_uri(args.output)
    prefix = prefix.rstrip("/") + "/"
    output_uri = f"s3://{bucket}/{prefix}"
    total_records = args.files * args.records_per_file

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

    while True:
        page = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1000)
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if not objects:
            break
        s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})

    started = time.perf_counter()
    print(f"Creating {total_records:,} records")
    print(f"Writing {args.files:,} uncompressed NDJSON objects to {output_uri}")

    connection = duckdb.connect(":memory:")
    try:
        configure_minio(connection)
        for file_number in range(args.files):
            first_id = file_number * args.records_per_file
            key = f"{prefix}part-{file_number:05d}.ndjson"
            uri = f"s3://{bucket}/{key}"
            file_started = time.perf_counter()

            connection.execute(
                f"""
                COPY (
                    {transaction_select(first_id, args.records_per_file)}
                ) TO {sql_string(uri)}
                (FORMAT JSON, ARRAY false)
                """
            )

            records_done = (file_number + 1) * args.records_per_file
            elapsed = time.perf_counter() - started
            print(
                f"Wrote {key} | {records_done:,}/{total_records:,} records | "
                f"file: {time.perf_counter() - file_started:.2f}s | "
                f"{records_done / elapsed:,.0f} records/sec"
            )
    finally:
        connection.close()

    total_bytes = 0
    object_count = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents", [])
        object_count += len(contents)
        total_bytes += sum(item["Size"] for item in contents)

    elapsed = time.perf_counter() - started
    print()
    print("Done.")
    print(f"Total records: {total_records:,}")
    print(f"Total files: {object_count:,}")
    print(f"Total size: {total_bytes / (1024**3):,.2f} GiB")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average throughput: {total_records / elapsed:,.0f} records/sec")


if __name__ == "__main__":
    main()

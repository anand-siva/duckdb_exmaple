# DuckDB: NDJSON vs. Parquet

This repository compares DuckDB query performance against the same dataset stored in two formats:

- Uncompressed newline-delimited JSON (NDJSON)
- Zstandard-compressed Parquet

Both datasets live in a local S3-compatible MinIO object store. DuckDB generates the records, writes both formats, and runs the same revenue-by-state aggregation directly against the objects in MinIO. There is no Spark cluster and no data is imported into a persistent DuckDB database.

## What this experiment measures

The experiment answers three questions:

1. How much storage does NDJSON use compared with compressed Parquet?
2. How long does DuckDB take to aggregate 100 million NDJSON records?
3. How long does the identical DuckDB query take against Parquet?

The data and query logic are deterministic, so both formats produce the same state counts and revenue totals. Only the storage format changes.

```text
                         ┌─ transactions-ndjson/*.ndjson ─┐
DuckDB data generator ───┤                                 ├── DuckDB aggregation
                         └─ transactions/*.parquet ────────┘
                                      MinIO
```

## Dataset

Each format contains:

- `1,000` objects
- `100,000` records per object
- `100,000,000` total records

Each transaction has this schema:

| Column | Type |
| --- | --- |
| `transaction_id` | `VARCHAR` |
| `customer_id` | `INTEGER` |
| `state` | `VARCHAR` |
| `product_category` | `VARCHAR` |
| `amount` | `DECIMAL(10,2)` |
| `created_at` | `TIMESTAMP` |

A record looks like this when represented as JSON:

```json
{
  "transaction_id": "uuid",
  "customer_id": 123456,
  "state": "MD",
  "product_category": "electronics",
  "amount": 149.95,
  "created_at": "2026-06-12T12:34:56.000000+00:00"
}
```

The objects are stored at:

| Format | MinIO location |
| --- | --- |
| Parquet | `s3://duckdb-demo/transactions/*.parquet` |
| NDJSON | `s3://duckdb-demo/transactions-ndjson/*.ndjson` |

## NDJSON and Parquet are fundamentally different

NDJSON is a row-oriented text format. Every line is an independent JSON object. It is easy for people to inspect, easy for applications to stream, and tolerant of records whose fields change over time. Those conveniences have a cost: every record repeats the field names, numbers and timestamps are stored as text, and an analytical engine must parse the JSON before it can use the values.

Parquet is a typed, column-oriented binary format designed for analytics. Values from the same column are stored together in row groups. DuckDB can read only the columns required by a query, use compact binary representations for numbers and timestamps, and apply encodings and compression to repeated values.

For this aggregation, DuckDB only needs `state` and `amount`. With NDJSON it still has to scan and parse the complete textual representation of all 100 million records. With Parquet it can avoid reading most of the other four columns. The ten possible state values also compress extremely well in a columnar representation.

| Characteristic | NDJSON | Parquet |
| --- | --- | --- |
| Layout | Row-oriented text | Column-oriented binary |
| Schema | Usually inferred while reading | Stored in file metadata |
| Repeated field names | Written in every record | Stored once as metadata |
| Compression in this example | None | Zstandard |
| Column projection | Must still parse each JSON record | Reads only selected columns |
| Human-readable | Yes | No |
| Best suited for | Logs, streaming, interchange | Analytical scans and aggregations |

## Prerequisites

- Python 3.10 or newer
- Docker with `docker compose`
- `curl`
- Enough free disk space for both 100-million-row datasets

The shell wrappers manage the Python virtual environment, dependencies, and MinIO startup. You do not need a global `python` command.

## Run the full experiment

### 1. Create the compressed Parquet dataset

```bash
./setup_test_data.sh
```

This creates `.venv`, installs the dependencies, starts MinIO, and writes 1,000 Zstandard-compressed Parquet objects.

### 2. Create the uncompressed NDJSON dataset

```bash
./run_seed_ndjson.sh
```

NDJSON is stored under a separate prefix, so this does not replace the Parquet dataset.

### 3. Query NDJSON with DuckDB

```bash
./run_query_ndjson.sh
```

DuckDB must scan and parse the complete NDJSON representation. The runner displays a progress bar because this is much slower than scanning Parquet.

### 4. Run the same query against Parquet

```bash
./run_query_parquet.sh
```

Parquet is columnar, so DuckDB can read only the `state` and `amount` columns required by the aggregation. Its metadata, binary types, and compression also reduce the number of bytes read.

Both query scripts print the same report:

```text
Revenue by state:
CA: $...
...

Transaction count by state:
CA: ...
...

Processed 100,000,000 records in ...s
```

## Query being compared

Conceptually, both scripts run this aggregation:

```sql
SELECT
    state,
    count(*) AS transaction_count,
    sum(amount) AS total_revenue
FROM dataset
GROUP BY state
ORDER BY state;
```

For NDJSON, `dataset` is `read_ndjson(...)`. For Parquet, it is `read_parquet(...)`. An explicit NDJSON schema avoids spending additional time inferring types.

## Current results

### Generating the datasets

The earlier Python implementation generated 100 million NDJSON records in approximately 10.3 minutes:

| Writer and format | Time | Throughput | Stored size |
| --- | ---: | ---: | ---: |
| Regular Python, NDJSON | 619.79 seconds | 161,345 records/sec | Not measured in this run |
| DuckDB, NDJSON | 189.42 seconds | 527,940 records/sec | 15.69 GiB |
| DuckDB, Parquet with ZSTD | 77.97 seconds | 1,282,609 records/sec | 2.92 GiB |

Using DuckDB to generate the same NDJSON dataset was `3.27x` faster than the regular Python implementation. It saved 430.37 seconds, reduced runtime by `69.4%`, and increased throughput by `227.2%`.

Writing directly to compressed Parquet was faster again. Compared with DuckDB writing NDJSON, Parquet generation was `2.43x` faster and reduced the output from 15.69 GiB to 2.92 GiB. That is 12.77 GiB less storage—an `81.4%` reduction, or about `5.37x` smaller.

### Querying the datasets

Both DuckDB queries ran the same aggregation and returned identical totals:

| Engine and format | Query time | Effective throughput |
| --- | ---: | ---: |
| Spark, historical NDJSON example | 76.5 seconds | 1.31 million records/sec |
| DuckDB, NDJSON | 67.3 seconds | 1.49 million records/sec |
| DuckDB, Parquet with ZSTD | 2.2 seconds | 45.45 million records/sec |

DuckDB scanning NDJSON was only modestly faster than the historical Spark result. The simpler deployment is still significant: DuckDB performed the query in one local process without a Spark master, workers, or distributed-job setup.

The Parquet result is the important comparison. DuckDB ran the same aggregation in 2.2 seconds instead of 67.3 seconds—about `30.6x` faster, with a `96.7%` reduction in query time. Across 1,000 objects and 100 million records, Parquet let DuckDB avoid most of the parsing and I/O required by NDJSON.

The Spark number is useful historical context, but it is not a controlled engine benchmark. The old Spark project generated random records and used a different execution environment. The controlled comparison in this repository is DuckDB reading NDJSON versus DuckDB reading Parquet generated from the same deterministic data.

These are single observed runs, not a formal benchmark. For more reliable measurements, run each query several times, report the median, and distinguish cold-cache from warm-cache runs.

## Run a small smoke test

The full experiment writes 200 million records in total and requires substantial time and storage. Validate the workflow first with two small objects per format:

```bash
./setup_test_data.sh --files 2 --records-per-file 1000
./run_seed_ndjson.sh --files 2 --records-per-file 1000
./run_query_ndjson.sh
./run_query_parquet.sh
```

Running a seed command again replaces the objects under that format's prefix.

## Project layout

- [`compose.yml`](compose.yml): local MinIO service
- [`seed_transactions.py`](seed_transactions.py): compressed Parquet generator
- [`seed_ndjson.py`](seed_ndjson.py): uncompressed NDJSON generator
- [`query_transactions.py`](query_transactions.py): Parquet aggregation
- [`query_ndjson.py`](query_ndjson.py): NDJSON aggregation
- [`setup_test_data.sh`](setup_test_data.sh): environment, MinIO, and Parquet setup
- [`run_seed_ndjson.sh`](run_seed_ndjson.sh): NDJSON seed wrapper
- [`run_query_ndjson.sh`](run_query_ndjson.sh): NDJSON query wrapper
- [`run_query_parquet.sh`](run_query_parquet.sh): Parquet query wrapper

## MinIO

The MinIO console is available at [http://localhost:9001](http://localhost:9001).

```text
Username: admin
Password: password123
```

## Cleanup

Stop MinIO while preserving the datasets:

```bash
docker compose down
```

Stop MinIO and delete both generated datasets:

```bash
docker compose down -v
```

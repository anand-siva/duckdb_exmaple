# DuckDB Parquet Example

This example uses DuckDB for both stages of a small analytics workflow:

1. Start a local S3-compatible MinIO object store.
2. Generate a synthetic transaction dataset with DuckDB and write it directly to Parquet in MinIO.
3. Query the remote Parquet file with DuckDB to calculate revenue and transaction counts by state.

Spark is not required. DuckDB handles both Parquet creation and analytics, while MinIO keeps the data in object storage.

## Project layout

- [`compose.yml`](compose.yml) runs MinIO locally.
- [`seed_transactions.py`](seed_transactions.py) generates the dataset with DuckDB and writes it to `s3://duckdb-demo/transactions/transactions.parquet`.
- [`query_transactions.py`](query_transactions.py) queries that Parquet object without importing it into a database first.
- [`setup_test_data.sh`](setup_test_data.sh) starts MinIO, creates a virtual environment, and seeds the data.
- [`requirements.txt`](requirements.txt) contains the Python dependency.

## Prerequisites

- Python 3.10 or newer
- Docker with `docker compose`
- `curl`

## Quick start

Start MinIO, create the environment, and seed one million transactions:

```bash
./setup_test_data.sh
```

Then query the generated Parquet file:

```bash
source .venv/bin/activate
python query_transactions.py
```

The query reports each state's transaction count and total revenue, followed by the overall row count and elapsed time.

## Choose the dataset size

The default is deliberately small enough for a quick local run. Pass a different row count to the setup script when you want a larger benchmark:

```bash
./setup_test_data.sh --rows 100000000
```

You can also run the seed step directly:

```bash
source .venv/bin/activate
python seed_transactions.py --rows 100000000
```

The seed command replaces the generated Parquet object when it is run again.

## Query a different Parquet object

Both a single object and a DuckDB-compatible S3 glob are supported:

```bash
python query_transactions.py s3://duckdb-demo/transactions/transactions.parquet
python query_transactions.py 's3://duckdb-demo/transactions/*.parquet'
```

DuckDB reads the Parquet data directly from MinIO through its `httpfs` extension. It uses Parquet metadata, column projection, and filter pushdown without requiring a separate load into a persistent `.duckdb` file.

## Data shape

Each generated row contains:

```text
transaction_id  VARCHAR
customer_id     INTEGER
state           VARCHAR
product_category VARCHAR
amount          DECIMAL(10,2)
created_at      TIMESTAMP
```

The generated values are deterministic, so seeding the same number of rows produces the same analytical results.

## Cleanup

Stop MinIO:

```bash
docker compose down
```

Stop MinIO and remove its generated data:

```bash
docker compose down -v
```

#!/usr/bin/env bash
# Резервная копия PostgreSQL. URL берётся из DATABASE_URL, секреты в скрипт не вшиты.
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Задайте DATABASE_URL" >&2
  exit 1
fi

output="${1:-backup-$(date -u +%Y%m%dT%H%M%SZ).dump}"
url="${DATABASE_URL/postgresql+psycopg/postgresql}"
pg_dump "$url" -Fc -f "$output"
echo "$output"

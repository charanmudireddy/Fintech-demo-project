#!/bin/bash
set -e

kubectl exec -n demo-project deployment/postgres -- \
  pg_dump -U loanuser loandb > backup.sql

echo "Backup saved to backup.sql"
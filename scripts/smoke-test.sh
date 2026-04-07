#!/bin/bash
set -e

curl http://localhost:5000/health
curl http://localhost:5000/ready
curl -X POST http://localhost:5000/loans \
  -H "Content-Type: application/json" \
  -d '{"borrower_name":"Test User","amount":15000,"status":"NEW"}'
curl http://localhost:5000/loans
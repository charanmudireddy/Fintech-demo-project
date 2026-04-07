from flask import Flask, request, jsonify
import os
import psycopg2
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
import logging
import json

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["endpoint"])

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "loandb")
DB_USER = os.getenv("DB_USER", "loanuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "loanpass")
DB_PORT = os.getenv("DB_PORT", "5432")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )


def wait_for_db():
    for i in range(20):
        try:
            conn = get_connection()
            conn.close()
            print("Database is ready")
            return
        except Exception:
            print(f"Waiting for database... {i + 1}/20")
            time.sleep(3)
    raise Exception("Database did not become ready in time")


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id SERIAL PRIMARY KEY,
            borrower_name VARCHAR(100) NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


@app.route("/health", methods=["GET"])
def health():
    REQUEST_COUNT.labels(method="GET", endpoint="/health", status="200").inc()
    return jsonify({"status": "ok"}), 200


@app.route("/ready", methods=["GET"])
def ready():
    start = time.time()
    try:
        conn = get_connection()
        conn.close()
        REQUEST_COUNT.labels(method="GET", endpoint="/ready", status="200").inc()
        REQUEST_LATENCY.labels(endpoint="/ready").observe(time.time() - start)
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        REQUEST_COUNT.labels(method="GET", endpoint="/ready", status="500").inc()
        REQUEST_LATENCY.labels(endpoint="/ready").observe(time.time() - start)
        return jsonify({"status": "not ready", "error": str(e)}), 500


@app.route("/loans", methods=["POST"])
def create_loan():
    start = time.time()
    data = request.get_json()
    borrower_name = data.get("borrower_name")
    amount = data.get("amount")
    status = data.get("status", "NEW")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO loans (borrower_name, amount, status) VALUES (%s, %s, %s) RETURNING id;",
        (borrower_name, amount, status)
    )
    loan_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    logger.info(json.dumps({
        "event": "loan_created",
        "borrower_name": borrower_name,
        "amount": amount,
        "status": status
    }))

    REQUEST_COUNT.labels(method="POST", endpoint="/loans", status="201").inc()
    REQUEST_LATENCY.labels(endpoint="/loans").observe(time.time() - start)

    return jsonify({
        "id": loan_id,
        "borrower_name": borrower_name,
        "amount": amount,
        "status": status
    }), 201


@app.route("/loans", methods=["GET"])
def get_loans():
    start = time.time()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, borrower_name, amount, status, created_at FROM loans ORDER BY id;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    loans = []
    for row in rows:
        loans.append({
            "id": row[0],
            "borrower_name": row[1],
            "amount": float(row[2]),
            "status": row[3],
            "created_at": row[4].isoformat()
        })

    logger.info(json.dumps({
        "event": "loans_listed",
        "count": len(loans)
    }))

    REQUEST_COUNT.labels(method="GET", endpoint="/loans", status="200").inc()
    REQUEST_LATENCY.labels(endpoint="/loans").observe(time.time() - start)

    return jsonify(loans), 200


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    wait_for_db()
    init_db()
    app.run(host="0.0.0.0", port=5000)
"""CI-only probe across a real PostgreSQL container restart; synthetic data only."""
import os
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app.db.migrate import migrate
from app.db.verify import verify_schema

url = os.environ["TEST_DATABASE_URL"]
if not conninfo_to_dict(url).get("dbname", "").endswith("_test"):
    raise SystemExit("Refusing a database that is not suffixed _test")
mode = sys.argv[1]
if mode == "write":
    migrate(url)
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO users(name,email,password_hash) VALUES ('Synthetic restart probe','restart@example.test','test-only-not-a-login')")
elif mode == "check":
    report = verify_schema(url)
    if not report["ok"]:
        raise SystemExit(str(report))
    with psycopg.connect(url) as conn:
        count = conn.execute("SELECT count(*) FROM users WHERE email='restart@example.test'").fetchone()[0]
        if count != 1:
            raise SystemExit("Committed record did not survive restart")
    print("PASS: six tables, migration ledger, pgvector, and committed record survived restart")
else:
    raise SystemExit("Expected write or check")

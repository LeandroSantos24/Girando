"""Corre las 50 verificaciones de reglas de la base (tests/sql/900_flujos.sql) sobre una base
limpia (solo migraciones, sin seeds), usando psql si está disponible."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import CREDS, HOST

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("psql"), reason="psql no instalado")
def test_sql_business_rules():
    user, pw = CREDS.split(":", 1)
    host, port = (HOST.split(":") + ["5432"])[:2]
    env = {**os.environ, "PGPASSWORD": pw}
    base = ["psql", "-h", host, "-p", port, "-U", user, "-v", "ON_ERROR_STOP=1", "-X", "-q"]

    def run(*args, db="postgres"):
        r = subprocess.run([*base, "-d", db, *args], capture_output=True, text=True, env=env, timeout=180)
        assert r.returncode == 0, r.stderr[-3000:]
        return r

    run("-c", "DROP DATABASE IF EXISTS girando_sqltest", "-c", "CREATE DATABASE girando_sqltest")
    for f in [*sorted((ROOT / "sql" / "0001_initial").glob("*.sql")), ROOT / "sql" / "0002_api_grants.sql"]:
        run("-f", str(f), db="girando_sqltest")
    r = run("-f", str(ROOT / "tests" / "sql" / "900_flujos.sql"), db="girando_sqltest")
    assert r.stderr.count("NOTICE:  ok") >= 50
    run("-c", "DROP DATABASE IF EXISTS girando_sqltest")

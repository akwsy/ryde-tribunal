"""Prepare an isolated submission database without touching company records."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]


def prepare(name,bundle):
    from database.importer.bundle import load_bundle
    from database.importer.persist import import_bundle
    payload=load_bundle(Path(bundle))
    if payload.manifest.get("synthetic") is not True:raise ValueError('Submission database accepts only synthetic bundles')
    if not re.fullmatch(r"ryde_tribunal_submission_[a-z0-9_]+_test",name) or len(name)>63:
        raise ValueError('Only a named submission test database is allowed')
    with psycopg.connect('postgresql:///postgres',autocommit=True) as conn:
        exists=conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone()
        if not exists:conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn='postgresql:///'+name
    for component in ('database','backend'):
        migration_dsn=dsn if component=='database' else dsn.replace('postgresql://','postgresql+psycopg://',1)
        subprocess.run([sys.executable,'-m','alembic','-c','alembic.ini','upgrade','head'],cwd=ROOT/component,
            env={**os.environ,'DATABASE_URL':migration_dsn,'PYTHONPATH':str(ROOT)},check=True)
    with psycopg.connect(dsn) as conn:
        for role in ('ryde_submission_writer','ryde_submission_importer'):
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT').format(sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(name),sql.Identifier(role)))
        conn.execute('GRANT USAGE ON SCHEMA tribunal TO ryde_submission_writer')
        conn.execute('GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA tribunal TO ryde_submission_writer')
        conn.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA tribunal TO ryde_submission_writer')
        conn.execute('GRANT ryde_backend_writer TO ryde_submission_writer')
        source=(ROOT/'database/roles/provision_import_role.sql').read_text()
        # Only reuse the scoped grant statements. Never alter an existing global production role.
        statements=source[source.index('GRANT CONNECT'):].split('-- Keep the legacy')[0]
        statements=statements.replace('ryde_data_importer','ryde_submission_importer').replace('DATABASE ryde_tribunal ','DATABASE '+name+' ')
        conn.execute(statements)
    result=import_bundle(dsn,payload)
    print('Submission database prepared; imported users',result.imported_user_count,'trips',result.imported_trip_count)
    return name


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',default='ryde_tribunal_submission_demo_test');p.add_argument('--bundle',required=True);a=p.parse_args();prepare(a.database,a.bundle)

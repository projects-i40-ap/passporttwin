"""Cross-platform helpers: python tools/dev.py start | demo. Requires Docker Compose."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def compose(*args,input_text=None):
    return subprocess.run(['docker','compose',*args],cwd=ROOT,input=input_text,text=True,check=True)


def sql(text):
    # Expand only the container's configured variables; do not interpolate .env values into shell code.
    compose('exec','-T','postgres','sh','-c',
        'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',input_text=text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','demo']);args=parser.parse_args()
    if not (ROOT/'.env').exists():
        shutil.copyfile(ROOT/'.env.example',ROOT/'.env')
        print('Creado .env local desde .env.example. Conserva esta configuración fuera de Git.')
    if args.action=='start':
        compose('up','-d','--wait','postgres')
        sql("SELECT 'CREATE DATABASE metabase' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='metabase')\\gexec\n")
        compose('up','-d','--build','backend','frontend','basyx-aas','metabase')
        print('Servicios iniciados. Usa las URLs de .env; revisa docker compose ps si alguno todavía está arrancando.')
    else:
        # Stop on migration failure; never drop tables or reset volumes.
        migration='\n'.join((ROOT/path).read_text() for path in (
            'infra/postgres/analytics_snapshot.sql','bi/sql/fleet_overview.sql','bi/sql/fleet_analytics.sql'))
        sql('BEGIN;\n'+migration+'\nCOMMIT;\n')
        compose('run','--rm','backend','python','-m','scripts.seed_demo')
        print('Para instalar las tarjetas de Metabase sigue bi/README.md; se requiere una conexión y colección autorizadas.')


if __name__=='__main__':main()

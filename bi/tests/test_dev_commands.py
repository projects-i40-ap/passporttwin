import importlib.util
from pathlib import Path
import sys
import subprocess
import pytest

spec=importlib.util.spec_from_file_location('dev_commands',Path(__file__).parents[2]/'tools/dev.py')
dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev)


def test_start_preserves_local_env_and_waits_for_database(monkeypatch,tmp_path):
    (tmp_path/'.env').write_text('LOCAL=value\n')
    monkeypatch.setattr(dev,'ROOT',tmp_path)
    calls=[];monkeypatch.setattr(dev,'compose',lambda *args,**kwargs:calls.append((args,kwargs)))
    monkeypatch.setattr(sys,'argv',['dev.py','start'])
    dev.main()
    assert (tmp_path/'.env').read_text()=='LOCAL=value\n'
    assert calls[0][0]==('up','-d','--wait','postgres')
    assert 'CREATE DATABASE metabase' in calls[1][1]['input_text']
    assert calls[2][0][:3]==('up','-d','--build')
    assert not any('down' in call[0] for call in calls)


def test_demo_stops_before_seeding_if_migration_fails(monkeypatch,tmp_path):
    (tmp_path/'.env').write_text('LOCAL=value\n')
    for path in ('infra/postgres/analytics_snapshot.sql','bi/sql/fleet_overview.sql','bi/sql/fleet_analytics.sql'):
        file=tmp_path/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('SELECT 1;')
    monkeypatch.setattr(dev,'ROOT',tmp_path);calls=[]
    def fail(*args,**kwargs):
        calls.append(args);raise subprocess.CalledProcessError(1,'docker')
    monkeypatch.setattr(dev,'compose',fail);monkeypatch.setattr(sys,'argv',['dev.py','demo'])
    with pytest.raises(subprocess.CalledProcessError):dev.main()
    assert len(calls)==1 and calls[0][0]=='exec'

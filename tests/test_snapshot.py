import datetime as dt
import importlib.util
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from snapshot_clusters import snapshot

def test_daily_snapshot_reuses_immutable_same_day(tmp_path,monkeypatch):
    calls=[]
    def fake_download(dataset,path):
        calls.append(path);path.write_bytes(b'actual source stand-in for unit test')
        return {'retrieved_at_utc':'2026-09-24T01:00:00Z'}
    monkeypatch.setattr('snapshot_clusters.download_dataset',fake_download)
    first=snapshot(tmp_path,dt.datetime(2026,9,24,1,tzinfo=dt.timezone.utc))
    second=snapshot(tmp_path,dt.datetime(2026,9,24,7,tzinfo=dt.timezone.utc))
    assert len(calls)==1 and first==second
    snapshot(tmp_path,dt.datetime(2026,9,25,1,tzinfo=dt.timezone.utc))
    assert len(calls)==2

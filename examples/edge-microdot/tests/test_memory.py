"""RSS measurement and the in-memory row and DuckDB limits."""
from __future__ import annotations

import zipfile
from pathlib import Path

from edge_microdot.cache import HotCache
from edge_microdot.fdd import FddEngine
from edge_microdot.history_store import HistoryStore
from edge_microdot.models import PointTarget
from edge_microdot.sources.fake import FakePollSource


def _rss_mb() -> float:
    """Current resident set, so an earlier test's peak does not fail this one."""
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024.0
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def test_rss_under_50_points(tmp_path):
    targets = [
        PointTarget(site="demo", device="10001", object_id=f"analog-input,{i}", units="C")
        for i in range(1, 51)
    ]
    hot = HotCache("dict")
    history = HistoryStore(tmp_path / "mem.duckdb")
    fdd = FddEngine(history=history)
    source = FakePollSource(targets)
    baseline = _rss_mb()
    samples = source.poll_once()
    hot.write(samples)
    history.stage(samples)
    history.flush()
    fdd.run()
    after = _rss_mb()
    delta = after - baseline
    print(f"\nMEMORY_RSS_MB idle-ish={after:.1f} delta_after_50pt_poll={delta:.1f}")
    assert len(samples) == 50
    assert after < 256, f"RSS {after:.1f} MB unexpectedly high on dev host"
    history.close()
    hot.close()


def test_ram_rows_and_duckdb_memory_limit(tmp_path):
    history = HistoryStore(tmp_path / "cap.duckdb", max_memory_rows=100, memory_limit_mb=64)
    history.conn.execute(
        """
        INSERT INTO fdd.sample_store
        SELECT 'demo', 'bacnet://1/analog-input,1',
               CURRENT_TIMESTAMP - INTERVAL 1 HOUR + (i * INTERVAL 1 SECOND),
               1.0, NULL, 'ok'
        FROM range(150) t(i)
        """
    )
    history.prune_memory()
    assert history.row_count() == 100
    setting = str(history.query("SELECT current_setting('memory_limit')")[0][0])
    assert "MiB" in setting
    assert float(setting.split()[0]) < 80
    history.close()


def test_export_zip_is_a_file_outside_the_lock(tmp_path):
    history = HistoryStore(tmp_path / "exp.duckdb")
    history.conn.execute(
        """
        INSERT INTO fdd.sample_store VALUES
          ('demo', 'bacnet://1/analog-input,1', TIMESTAMPTZ '2026-11-26 00:00:00+00', 21.0, NULL, 'ok')
        """
    )
    path = history.export_bundle_file([], hours=24)
    try:
        assert path.parent == history.snapshot_dir / "exports"
        assert not (history.snapshot_dir / "exports").joinpath(f".staging-{path.stem}").exists()
        with zipfile.ZipFile(path) as zf:
            assert set(zf.namelist()) == {
                "input_sample.parquet",
                "point.parquet",
                "rule_result.parquet",
            }
    finally:
        path.unlink(missing_ok=True)
        history.close()


def test_rss_after_250k_rows_and_export(tmp_path):
    history = HistoryStore(tmp_path / "big.duckdb", memory_limit_mb=256, max_memory_rows=250_000)
    history.conn.execute(
        """
        INSERT INTO fdd.point (site_id, point_key, kind)
        VALUES ('demo', 'bacnet://1/analog-input,1', 'numeric')
        """
    )
    history.conn.execute(
        """
        INSERT INTO fdd.sample_store
        SELECT 'demo', 'bacnet://1/analog-input,1',
               TIMESTAMPTZ '2026-11-20 00:00:00+00' + (i * INTERVAL 1 SECOND),
               i::DOUBLE, NULL, 'ok'
        FROM range(250000) t(i)
        """
    )
    path = history.export_bundle_file([], hours=168)
    path.unlink(missing_ok=True)
    after = _rss_mb()
    print(f"\nMEMORY_RSS_MB after_250k_export={after:.1f}")
    assert history.row_count() == 250_000
    assert after < 400, f"RSS {after:.1f} MB exceeds the budget under the 512m container cap"
    history.close()
from pathlib import Path

from gitpulse.storage import SnapshotStore


def test_saves_and_reads_snapshots_in_collection_order(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "test.sqlite3")
    store.save("owner", "tap", "views", {"views": [{"count": 4, "uniques": 3}]})
    store.save("owner", "tap", "views", {"views": [{"count": 9, "uniques": 6}]})

    rows = store.history("owner", "tap", "views")

    assert len(rows) == 2
    assert rows[0]["views"][0]["count"] == 4
    assert rows[1]["views"][0]["count"] == 9
    assert "fetched_at" in rows[0]


def test_history_is_scoped_to_repository_and_metric(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "test.sqlite3")
    store.save("owner", "tap", "clones", {"clones": []})

    assert store.history("owner", "other", "clones") == []
    assert store.history("owner", "tap", "views") == []

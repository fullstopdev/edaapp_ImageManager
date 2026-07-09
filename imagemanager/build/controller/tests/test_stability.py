"""Regression tests for incidents documented in docs/STABILITY.md."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import main


def test_status_update_skips_unchanged_payload(monkeypatch):
    """Reconcile-storm guard: identical status digest must not trigger a PUT."""
    calls = []

    def fake_read_cr(*_args, **_kwargs):
        return {"metadata": {"name": "default"}, "status": {}}

    def fake_update(*_args, **_kwargs):
        calls.append(1)

    monkeypatch.setattr(main.k8s, "read_cr", fake_read_cr)
    monkeypatch.setattr(main.k8s, "update_cr_status", fake_update)
    monkeypatch.setattr(main.uploads, "storage_stats", lambda: (0, 0))

    fixed = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    tracked = [{"name": "img1", "downloadStatus": "Available"}]
    main._last_status_hash = None
    main._update_status("ok", "All systems operational", tracked)
    main._update_status("ok", "All systems operational", tracked)
    assert len(calls) == 1


def test_status_payload_digest_changes_when_tracked_changes(monkeypatch):
    """Guard must allow PUT when artifact rows actually change."""
    monkeypatch.setattr(main.uploads, "storage_stats", lambda: (1, 100))

    fixed = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    a = main._status_payload("ok", "msg", [{"name": "a", "downloadStatus": "Available"}])
    b = main._status_payload("ok", "msg", [{"name": "b", "downloadStatus": "Available"}])
    da = hashlib.sha256(json.dumps(a, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    db = hashlib.sha256(json.dumps(b, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert da != db


def test_node_agent_daemonset_labels_and_teardown():
    """Node-agent must carry app labels and avoid blocking preStop hooks."""
    repo_root = Path(__file__).resolve().parents[4]
    text = (repo_root / "imagemanager" / "manifests" / "daemonset.yaml").read_text()
    assert "eda.nokia.com/app: eda-imagemanager" in text
    assert "eda.nokia.com/component: node-agent" in text
    assert "terminationGracePeriodSeconds: 10" in text
    assert "preStop:" not in text


def test_imagemanager_viewer_clusterrole_exists():
    """imagemanager-viewer ClusterRole with HttpProxy urlRules."""
    repo_root = Path(__file__).resolve().parents[4]
    text = (repo_root / "imagemanager" / "manifests" / "eda_viewer_role.yaml").read_text()
    assert "name: imagemanager-viewer" in text
    assert "/core/httpproxy/v1/imagemanager" in text

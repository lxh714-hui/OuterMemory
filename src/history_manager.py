from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from repository_paths import repository_root


EVENT_ID_PATTERN = re.compile(r"evt_[0-9a-f]{32}\Z")


class HistoryError(Exception):
    pass


def validate_event_id(event_id):
    if not isinstance(event_id, str) or not EVENT_ID_PATTERN.fullmatch(event_id):
        raise HistoryError("invalid event id")
    return event_id


class _HistoryRepository:
    """Internal persistence for governed mutation and rollback orchestration."""

    def __init__(self, root=None):
        self.root = repository_root(root)
        self.memory_root = (self.root / "memory").resolve()
        self.history_root = self.root / "history"
        self.snapshot_root = (self.history_root / "snapshots").resolve()
        self.events_root = (self.history_root / "events").resolve()
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.events_root.mkdir(parents=True, exist_ok=True)

    def snapshot_targets(self, event_id, targets):
        validate_event_id(event_id)
        snapshot_dir = self._snapshot_dir(event_id)
        before_dir = snapshot_dir / "before"
        snapshot_dir.mkdir(parents=True, exist_ok=False)
        manifest = {"event_id": event_id, "targets": []}
        for target in targets:
            relative, source = self._trusted_path(target)
            existed = source.is_file()
            manifest["targets"].append({"path": relative.as_posix(), "existed": existed})
            if existed:
                destination = before_dir / relative.relative_to("memory")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        self._write_json(snapshot_dir / "manifest.json", manifest)
        return snapshot_dir.relative_to(self.root).as_posix()

    def restore_for_governed_operation(self, snapshot_ref):
        snapshot_dir = self._snapshot_reference(snapshot_ref)
        with (snapshot_dir / "manifest.json").open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        for item in manifest["targets"]:
            relative, target = self._trusted_path(item["path"])
            if item["existed"]:
                source = snapshot_dir / "before" / relative.relative_to("memory")
                if not source.is_file():
                    raise HistoryError(f"snapshot file missing: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()

    def write_event(self, event):
        self._write_json(self._event_path(event["event_id"]), event)

    def load_event(self, event_id):
        path = self._event_path(event_id)
        if not path.is_file():
            raise HistoryError(f"history event not found: {event_id}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def find_applied_proposal(self, proposal_id):
        for event in self._events():
            if event.get("kind") == "mutation" and event.get("proposal_id") == proposal_id and event.get("state") in {"applied", "rolled_back"}:
                return event
        return None

    def has_unresolved_recovery(self):
        return any(event.get("state") == "recovery_required" for event in self._events())

    def has_rollback_for(self, event_id):
        return any(
            event.get("kind") == "rollback"
            and event.get("rollback_of") == event_id
            and event.get("state") in {"prepared", "applied", "recovery_required"}
            for event in self._events()
        )

    def _events(self):
        for path in self.events_root.glob("*.json"):
            with path.open("r", encoding="utf-8") as handle:
                yield json.load(handle)

    def _event_path(self, event_id):
        validate_event_id(event_id)
        path = (self.events_root / f"{event_id}.json").resolve()
        if not path.is_relative_to(self.events_root):
            raise HistoryError("event id escapes event storage")
        return path

    def _snapshot_dir(self, event_id):
        path = (self.snapshot_root / event_id).resolve()
        if not path.is_relative_to(self.snapshot_root):
            raise HistoryError("event id escapes snapshot storage")
        return path

    def _snapshot_reference(self, snapshot_ref):
        expected = self.snapshot_root
        path = (self.root / snapshot_ref).resolve()
        if not path.is_relative_to(expected):
            raise HistoryError("invalid snapshot reference")
        return path

    def _trusted_path(self, path):
        candidate = Path(path)
        if candidate.is_absolute() or not candidate.parts or candidate.parts[0] != "memory":
            raise HistoryError("invalid trusted-memory path")
        resolved = (self.root / candidate).resolve()
        if not resolved.is_relative_to(self.memory_root):
            raise HistoryError("trusted-memory path escapes memory root")
        return candidate, resolved

    @staticmethod
    def timestamp():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _write_json(path, value):
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(path)

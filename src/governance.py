"""Human-attention governance state; this module never writes trusted memory."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from memory_loader import MemoryLoader
from repository_paths import repository_root


LOW_MILESTONE_START = 5
LOW_BATCH_SIZE = 10
STARTUP_SCAN_INTERVAL = timedelta(hours=24)
OUTDATED_AFTER = timedelta(days=365)


class GovernanceError(Exception):
    pass


class GovernanceService:
    """Persists requests separately from trusted memory and proposals."""

    def __init__(self, root=None):
        self.root = repository_root(root)
        self.state_root = self.root / ".outermemory"
        self.path = self.state_root / "governance.json"

    def record_retrieval(self, results):
        state = self._load()
        generated = []
        for result in results:
            item = result["item"]
            memory_id = item["id"]
            retrieval = state["retrievals"].setdefault(memory_id, {"count": 0, "emitted_milestones": []})
            retrieval["count"] += 1
            count = retrieval["count"]
            if self._is_milestone(count) and count not in retrieval["emitted_milestones"]:
                retrieval["emitted_milestones"].append(count)
                generated.append(self._request(state, "low", "retrieval_milestone", {
                    "memory_id": memory_id, "category": item["category"], "path": item["path"],
                    "retrieval_count": count, "milestone": count,
                    "note": "Retrieval frequency is an attention signal, not a confidence score.",
                }))
        announcement = self._announce_low_batch_if_ready(state)
        self._save(state)
        return {"requests": generated, "announcement": announcement}

    def contextual_self_check(self, results):
        """Create immediate attention requests for conservative retrieval-context evidence."""
        state = self._load()
        generated = []
        items = [result["item"] for result in results]
        findings = SelfCheckEngine(items, items).inspect({"outdated", "duplicates"})
        for issue_type, group in findings.items():
            for finding in group:
                # "overlap" is the immediate attention presentation of the
                # shared engine's duplicate/overlap evidence.
                channel_issue = "overlap" if issue_type == "duplicates" else issue_type
                generated.append(self._request_once(
                    state, "immediate", channel_issue, sorted(finding["memory_ids"]), finding
                ))
        generated = [request for request in generated if request is not None]
        self._save(state)
        return generated

    def full_scan(self):
        """Run the shared read-only inspection engine and only then record success."""
        state = self._load()
        memory = MemoryLoader(repository_root_path=self.root).load()
        items = [item for category in memory.values() for item in category.values()]
        findings = SelfCheckEngine(items, items).inspect()
        completed = self._timestamp()
        state["last_successful_scan"] = completed
        state["latest_scan"] = {"completed_at": completed, "findings": findings}
        self._save(state)
        return {"completed_at": completed, "findings": findings}

    def startup_scan(self):
        state = self._load()
        previous = self._parse_timestamp(state.get("last_successful_scan"))
        if previous and datetime.now(timezone.utc) - previous < STARTUP_SCAN_INTERVAL:
            return {"ran": False, "last_successful_scan": state["last_successful_scan"]}
        # Do not catch errors: no success timestamp is persisted for an interrupted,
        # invalid, or failed scan.
        result = self.full_scan()
        return {"ran": True, **result}

    def pending_requests(self, issue_type=None):
        state = self._load()
        requests = [request for request in state["requests"] if request["resolution"]["status"] == "pending"]
        if issue_type:
            requests = [request for request in requests if request["issue_type"] == issue_type]
        return requests

    def request(self, request_id):
        for request in self._load()["requests"]:
            if request["request_id"] == request_id:
                return request
        raise GovernanceError("governance request not found")

    def resolve_request(self, request_id, resolution="reviewed"):
        if resolution not in {"reviewed", "dismissed"}:
            raise GovernanceError("invalid request resolution")
        state = self._load()
        for request in state["requests"]:
            if request["request_id"] == request_id:
                if request["resolution"]["status"] != "pending":
                    raise GovernanceError("governance request is already resolved")
                request["resolution"] = {"status": resolution, "timestamp": self._timestamp()}
                self._save(state)
                return request
        raise GovernanceError("governance request not found")

    def resolve_many(self, request_ids, resolution):
        """Explicit human group handling; never a trusted-memory mutation."""
        if resolution not in {"reviewed", "dismissed"} or not request_ids:
            raise GovernanceError("invalid bulk request resolution")
        if len(set(request_ids)) != len(request_ids):
            raise GovernanceError("request group contains duplicates")
        state = self._load()
        selected = [request for request in state["requests"] if request["request_id"] in request_ids]
        if len(selected) != len(request_ids):
            raise GovernanceError("governance request not found")
        if any(request["resolution"]["status"] != "pending" for request in selected):
            raise GovernanceError("only pending governance requests may be resolved")
        timestamp = self._timestamp()
        for request in selected:
            request["resolution"] = {"status": resolution, "timestamp": timestamp}
        self._save(state)
        return selected

    def latest_scan(self, issue_type=None, finding_id=None):
        scan = self._load().get("latest_scan")
        if not scan:
            return None
        findings = scan["findings"]
        if finding_id:
            for group in findings.values():
                for finding in group:
                    if finding["finding_id"] == finding_id:
                        return finding
            raise GovernanceError("scan finding not found")
        if issue_type:
            return {issue_type: findings.get(issue_type, [])}
        return scan

    def trace(self, identifier):
        """Human-facing, read-only provenance lookup across attention/proposal/history."""
        from history_manager import HistoryError, _HistoryRepository
        from proposal_store import _ProposalRepository, ProposalError
        proposals = _ProposalRepository(self.root)
        history = _HistoryRepository(self.root)
        if identifier.startswith("gov_"):
            request = self.request(identifier)
            linked = proposals.find_by_source_request(identifier)
            return {
                "request_id": identifier,
                "attention_status": request["resolution"]["status"],
                "evidence": request["evidence"],
                "linked_proposals": [self._proposal_trace(proposal, history) for proposal in linked],
            }
        if identifier.startswith("prop_"):
            try:
                proposal = proposals.load(identifier)
            except ProposalError as error:
                raise GovernanceError(str(error)) from error
            return self._proposal_trace(proposal, history)
        if identifier.startswith("evt_"):
            try:
                event = history.load_event(identifier)
            except HistoryError as error:
                raise GovernanceError(str(error)) from error
            return {"event_id": event["event_id"], "proposal_id": event.get("proposal_id"), "source_request_ids": event.get("source_request_ids", []), "state": event.get("state")}
        raise GovernanceError("trace identifier must be a governance request, proposal, or event id")

    @staticmethod
    def _proposal_trace(proposal, history):
        event_id = proposal.get("applied_event_id")
        event = history.load_event(event_id) if event_id else None
        return {
            "proposal_id": proposal["proposal_id"], "status": proposal["status"],
            "source_request_ids": proposal.get("source_request_ids", []),
            "history_event_id": event_id, "history_state": event.get("state") if event else None,
        }

    def _request_once(self, state, channel, issue_type, subjects, evidence):
        key = f"{channel}:{issue_type}:{':'.join(subjects)}"
        for request in state["requests"]:
            if request.get("deduplication_key") == key and request["resolution"]["status"] == "pending":
                return None
        return self._request(state, channel, issue_type, evidence, key)

    def _request(self, state, channel, issue_type, evidence, deduplication_key=None):
        request = {
            "request_id": f"gov_{uuid4().hex}", "channel": channel, "issue_type": issue_type,
            "created_at": self._timestamp(), "evidence": evidence,
            "announcement": {"status": "unannounced", "batch_id": None, "announced_at": None},
            "resolution": {"status": "pending", "timestamp": None},
            "deduplication_key": deduplication_key,
        }
        if channel == "immediate":
            request["announcement"] = {"status": "announced", "batch_id": None, "announced_at": request["created_at"]}
        state["requests"].append(request)
        return request

    def _announce_low_batch_if_ready(self, state):
        candidates = [
            request for request in state["requests"]
            if request["channel"] == "low"
            and request["announcement"]["status"] == "unannounced"
            and request["resolution"]["status"] == "pending"
        ]
        if len(candidates) < LOW_BATCH_SIZE:
            return None
        batch = candidates[:LOW_BATCH_SIZE]
        batch_id = f"batch_{uuid4().hex}"
        announced_at = self._timestamp()
        for request in batch:
            request["announcement"] = {"status": "announced", "batch_id": batch_id, "announced_at": announced_at}
        report = {"batch_id": batch_id, "announced_at": announced_at, "request_ids": [request["request_id"] for request in batch]}
        state["announcements"].append(report)
        return report

    @staticmethod
    def _is_milestone(count):
        return count >= LOW_MILESTONE_START and count % LOW_MILESTONE_START == 0 and (count // LOW_MILESTONE_START & (count // LOW_MILESTONE_START - 1)) == 0

    def _load(self):
        if not self.path.is_file():
            return {"version": 1, "retrievals": {}, "requests": [], "announcements": [], "last_successful_scan": None, "latest_scan": None}
        with self.path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, state):
        self.state_root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(self.path)

    @staticmethod
    def _parse_timestamp(value):
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()


class SelfCheckEngine:
    """One conservative detector used for contextual and full-library scopes."""

    ISSUE_TYPES = {"duplicates", "outdated", "orphaned", "conflicting"}

    def __init__(self, items, library_items):
        self.items = items
        self.library_ids = {item["id"] for item in library_items}

    def inspect(self, issue_types=None):
        """Return grouped findings for the requested scope without mutation."""
        issue_types = set(issue_types or self.ISSUE_TYPES)
        findings = {issue_type: [] for issue_type in self.ISSUE_TYPES}
        for index, item in enumerate(self.items):
            last_used = GovernanceService._parse_timestamp(item["data"].get("Metadata", {}).get("last_used", item.get("last_used", "")))
            if "outdated" in issue_types and last_used and datetime.now(timezone.utc) - last_used > OUTDATED_AFTER:
                findings["outdated"].append(_finding("outdated", [item["id"]], "heuristic", "last_used is more than 365 days old; content may still be valid."))
            related = item["data"].get("Related", [])
            # The parser represents bullet sections as lists. Treat a non-bullet
            # Related section as one malformed/unresolved reference rather than
            # iterating its characters.
            related = _as_list(related)
            missing = sorted(str(reference) for reference in related if reference not in self.library_ids)
            if "orphaned" in issue_types and missing:
                findings["orphaned"].append(_finding("orphaned", [item["id"]], "schema", "Related references do not resolve to trusted-memory items.", {"missing_related_ids": missing}))
            for other in self.items[index + 1:]:
                evidence = self._overlap_evidence(item, other)
                if "duplicates" in issue_types and evidence:
                    findings["duplicates"].append(_finding("duplicates", evidence["memory_ids"], "heuristic", evidence["heuristic"], evidence))
                conflict = _conflict(item, other)
                if "conflicting" in issue_types and conflict:
                    findings["conflicting"].append(_finding("conflicting", [item["id"], other["id"]], "heuristic", conflict))
        return findings

    @staticmethod
    def _overlap_evidence(item, other):
        description = _normalise(item["data"].get("Description", ""))
        other_description = _normalise(other["data"].get("Description", ""))
        if description and description == other_description:
            return {"memory_ids": [item["id"], other["id"]], "heuristic": "Descriptions are identical after whitespace/case normalization."}
        aliases = _as_list(item["data"].get("Aliases", []))
        other_aliases = _as_list(other["data"].get("Aliases", []))
        shared = sorted({alias.lower() for alias in aliases} & {alias.lower() for alias in other_aliases})
        if shared:
            return {"memory_ids": [item["id"], other["id"]], "heuristic": "Items share aliases; this indicates possible overlap, not a proven duplicate.", "shared_aliases": shared}
        return None


def _finding(issue_type, memory_ids, certainty, summary, evidence=None):
    key = f"{issue_type}:{':'.join(sorted(memory_ids))}:{summary}"
    return {"finding_id": f"finding_{uuid4().hex}", "issue_type": issue_type, "memory_ids": memory_ids, "certainty": certainty, "summary": summary, "evidence": evidence or {}, "deduplication_key": key}


def _conflict(item, other):
    key_values = item["data"].get("Metadata", {})
    other_values = other["data"].get("Metadata", {})
    for key in set(key_values) & set(other_values):
        if key not in {"id", "frequency", "last_used"} and key_values[key] and other_values[key] and key_values[key] != other_values[key]:
            return f"Both items define Metadata.{key} with different values; this may be a conflict."
    return None


def _normalise(value):
    return re.sub(r"\s+", " ", value).strip().lower()


def _as_list(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return [value] if isinstance(value, str) and value.strip() else []

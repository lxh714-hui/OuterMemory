# OuterMemory AI CLI

`src/outermemory_cli.py` is the JSON command-line adapter for the project-scoped, AI-facing `OuterMemory` interface. It is intended for AI agents and other programmatic callers. Memory belongs to the selected project root, not to a user, agent, or model.

Run commands from the repository root with `python src/outermemory_cli.py`. Use `--root PATH` before the command to operate on another project root; when omitted, the repository containing the CLI is used.

Successful commands write one JSON value to standard output. Operational failures write a JSON object such as `{"error": "..."}` to standard error and return a nonzero status. Argument errors use the same JSON error shape.

## `retrieve`

Purpose: retrieve relevant records from the project's memory. Retrieval is broad and read-only.

Syntax:

```text
python src/outermemory_cli.py [--root PATH] retrieve QUESTION [--topk COUNT]
```

Arguments:

- `QUESTION` is the query text.
- `--topk COUNT` limits returned records; it defaults to `5`.

Example:

```text
python src/outermemory_cli.py --root D:\projects\example retrieve "demo feature" --topk 3
```

Output shape: a JSON array of ranked results. Each result has a numeric `score` and an `item` containing the loaded memory record, including `id`, `category`, `path`, `filename`, `frequency`, `last_used`, and parsed record `data`.

```json
[
  {
    "score": 1,
    "item": {
      "id": "v_DEMO",
      "category": "variables",
      "path": "variables/v_DEMO.md",
      "filename": "v_DEMO.md",
      "frequency": 0,
      "last_used": "",
      "data": {"Metadata": {"id": "v_DEMO"}, "Description": "..."}
    }
  }
]
```

## `propose`

Purpose: create a pending proposal for a governed memory change. Creating a proposal is not a trusted-memory mutation.

Syntax:

```text
python src/outermemory_cli.py [--root PATH] propose OPERATION --category CATEGORY --id MEMORY_ID [--change JSON_OBJECT] [--reason TEXT]
```

Arguments:

- `OPERATION` is one of `create`, `update`, `delete`, or `merge`.
- `--category CATEGORY` is required and must name a project memory category.
- `--id MEMORY_ID` is required and is the target logical memory ID.
- `--change JSON_OBJECT` is an optional JSON object and defaults to `{}`.
- `--reason TEXT` is optional.

Example:

```text
python src/outermemory_cli.py propose create --category variables --id v_DEMO --change "{\"content\": \"# Metadata\\n\\nid: v_DEMO\\nfrequency: 0\\nlast_used:\\n\\n# Description\\n\\nDemo feature setting\\n\"}" --reason "Record the demo feature setting"
```

Output shape: a JSON proposal object. New proposals have `status` set to `pending`; they are stored as proposals, not applied to trusted memory.

```json
{
  "proposal_id": "prop_<32 hexadecimal characters>",
  "operation": "create",
  "target": {"category": "variables", "id": "v_DEMO"},
  "change": {"content": "..."},
  "reason": "Record the demo feature setting",
  "timestamp": "2026-01-01T00:00:00+00:00",
  "status": "pending",
  "decision_timestamp": null,
  "applied_event_id": null
}
```

## `proposal-status`

Purpose: inspect the governance status of an existing proposal.

Syntax:

```text
python src/outermemory_cli.py [--root PATH] proposal-status PROPOSAL_ID
```

Arguments:

- `PROPOSAL_ID` is the proposal identifier, in the form `prop_` followed by 32 hexadecimal characters.

Example:

```text
python src/outermemory_cli.py proposal-status prop_0123456789abcdef0123456789abcdef
```

Output shape:

```json
{
  "proposal_id": "prop_0123456789abcdef0123456789abcdef",
  "status": "pending",
  "applied_event_id": null
}
```

## Governance boundary

This AI-facing CLI intentionally does **not** expose `approve`, `reject`, `apply`, or `rollback`. Those are human-facing governance capabilities. The CLI supports broad retrieval and proposal creation, while persistence into trusted project memory remains governed.

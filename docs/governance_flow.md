# OuterMemory governance flow

OuterMemory memory belongs to the project. It is not owned by a user, agent, or model. The governing principle is **broad retrieval, governed persistence**: AI-facing callers may search memory and create proposals, but they do not receive authority to decide or perform trusted-memory mutations.

## Capability boundary

The AI-facing `OuterMemory` interface and JSON CLI provide:

- `retrieve`
- `propose`
- `proposal-status`

The separate human-facing governance interface in `src/main.py` provides:

- `approve`
- `reject`
- `apply`
- `rollback`

Approval authority must not be exposed through the AI-facing CLI.

## Mutation lifecycle

```text
AI proposes
    -> pending proposal
    -> explicit human approval
    -> controlled apply
    -> history event
    -> trusted project memory
```

1. An AI-facing caller uses `propose`. The proposal is recorded with status `pending`; proposal creation is not equivalent to trusted-memory mutation.
2. A human uses the human-facing interface to approve or reject the pending proposal. The current implementation asks for typed confirmation before approval or rejection.
3. After approval, a human-facing `apply` invokes the controlled writer. It accepts only approved proposals, validates the resulting memory, snapshots affected paths, applies the validated plan, and records a mutation history event.
4. The proposal is then associated with the applied event, and the resulting records are trusted project memory.

Approval and application are separate steps. An approved proposal is eligible for controlled application, but approval alone does not alter memory.

## Rollback lifecycle

```text
human-confirmed rollback
    -> new history event
    -> trusted memory restored
```

A human invokes `rollback` for an applied mutation event and confirms the action. The controlled writer snapshots current affected paths, restores the original event's snapshot, writes a new rollback history event, and marks the original mutation as rolled back. Rollback preserves audit history rather than erasing it.

The implementation blocks further governed mutations when recovery is required after a failed restoration.

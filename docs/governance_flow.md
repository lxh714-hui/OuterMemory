# OuterMemory governance flow

OuterMemory memory belongs to the project. It is not owned by a user, agent, or model. The governing principle is **broad retrieval, governed persistence**: human-governed persistence with risk-aware attention management. AI-facing callers may search memory and create proposals, but they do not receive authority to decide or perform trusted-memory mutations.

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

## Attention channels, with one authority boundary

Risk and batching determine when governance is presented, never who may write trusted memory.

```text
low-risk retrieval milestone (5, 10, 20, 40, ...) -> pending request -> announce in one batch of 10

current retrieval items -> contextual scope --┐
                                               ├-> shared Self-Check Engine -> immediate request / grouped scan report
whole library          -> full-library scope --┘                         |
                                                 proposal, only if a human requests action
                                                                         |
                                      explicit human approval -> controlled apply -> history
```

Low-risk counts continue increasing regardless of whether a request is announced or resolved. Each milestone is emitted once, while pending request resolution and batch-announcement state remain independent. Immediate requests never enter the low-risk batch queue.

One `SelfCheckEngine` supplies both scopes; scope controls its item set and presentation, rather than selecting unrelated detection code. The contextual scope evaluates only current retrieval items and surfaces outdated/overlap evidence as immediate requests. Full-library scope reports duplicates, outdated items, orphaned items, and conflicts by group or individual finding. Missing `Related` references are directly observable; old `last_used` values, description/alias overlap, and optional metadata disagreements are conservative heuristics and are labeled as such. A scan does not create proposals or mutate trusted memory.

`last_successful_scan` is persisted only after the scan loads and inspects the complete library successfully. Errors, interruption, and validation failure leave it untouched, so startup retries later.

## Human review modes

Human-facing governance supports individual proposal approval/rejection and group `approve-all`/`reject-all` decisions. Governance requests are only attention objects, so their group operations are `review-all` and `dismiss-all`, never approval of a memory mutation. Bulk operations require a secondary typed confirmation, validate the selected group as pending, and do not apply mutations. Individual review is naturally pausable: only named items are handled and every unprocessed item remains pending.

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

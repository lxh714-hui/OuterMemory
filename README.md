# OuterMemory

**A human-governed persistent memory layer for AI Coding.**

OuterMemory is an experimental external long-term memory system designed to make coding assistants more persistent, auditable, and independent of any specific model or agent.

Its core idea is simple:

> **Memory > Agent > Model**

Models can change. Agents can change.  
Project memory should remain.

---

## Why OuterMemory?

AI coding assistants are powerful, but their working context is temporary.

Across sessions, tools, or models, they may lose track of:

- project conventions,
- important variables and paths,
- architectural decisions,
- reusable functions,
- relationships between components,
- and previously established constraints.

OuterMemory treats this information as a persistent project asset rather than something owned by a particular model or conversation.

At the same time, persistent memory introduces another problem:

> If an AI can freely rewrite its own long-term memory, incorrect information can become persistent truth.

OuterMemory therefore separates **retrieval** from **persistence**.

> **Broad retrieval, governed persistence.**

AI should be able to search widely for useful information.  
But trusted long-term memory is changed only through an explicit human-governed process.

---

## Core Principles

### 1. Memory is independent of the model

Memory is stored outside the model in human-readable files.

A project should be able to switch models or agents without losing its long-term memory.

```text
Memory
  ↑
Agent
  ↑
Model
```

The memory layer is the stable component.

### 2. AI can read, but trusted memory is governed

The implemented retrieval and relation-expansion components may be used by an AI-facing integration to:

- retrieve trusted memory,
- inspect relationships between memory entries.

`ProposalService` provides proposal creation and status inspection. Caller integration that combines retrieval with these proposal capabilities is not yet implemented.

Trusted-memory mutation follows a controlled path:

```text
Proposal
   ↓
Human Approval
   ↓
Controlled Mutation
   ↓
History
   ↓
Trusted Memory
```

Approval and application are intentionally separate operations.

### 3. Memory changes are traceable and reversible

Before a governed mutation changes trusted memory, OuterMemory creates a minimal snapshot of the affected state.

This allows changes to be traced and rolled back.

```text
Before State
     ↓
 Snapshot
     ↓
 Mutation
     ↓
 History Event
```

Rollback is itself governed and recorded.

### 4. Retrieval power and write authority are separate

Restricting memory writes should not require restricting the AI's ability to obtain information.

The intended architecture allows AI systems to eventually retrieve information from sources such as:

```text
Trusted Memory
Documentation
GitHub repositories
Web sources
Papers
External databases
APIs
```

External information may be used during reasoning without automatically becoming trusted memory.

Persistence remains a separate decision.

---

## Current Architecture

The implemented trusted-memory retrieval components are:

```text
Markdown Memory
      ↓
MemoryParser
      ↓
MemoryLoader
      ↓
MemoryQuery
      ↓
MemoryRetriever
      ↓
Ranked Memory Results
```

These components can produce ranked results when invoked by a caller; a complete user-query orchestration layer is not yet implemented.

The governed mutation path is:

```text
Caller / Future AI
        ↓
ProposalService
        ↓
Pending Proposal
        ↓
HumanProposalDecisions
        ↓
Approved Proposal
        ↓
ControlledMemoryWriter
        ↓
History + Snapshot
        ↓
Trusted Memory
```

Rollback restores the recorded pre-mutation state through the governed history mechanism.

---

## Memory Structure

Trusted memory supports four schema categories. The currently populated physical directories are:

```text
memory/
├── variables/
├── resources/
└── standards/
```

`functions` is a supported schema category and can be created and populated later.

The documented ID-prefix convention is:

| Category | Prefix | Example |
|---|---|---|
| Variables | `v_` | `v_demo_feature` |
| Resources | `r_` | `r_demo_workspace` |
| Functions | `f_` | `f_example` |
| Standards | `s_` | `s_demo_conventions` |

Current validation accepts general logical IDs and does not enforce category-specific prefixes.

Memory entries are stored as Markdown so that both humans and machines can inspect them directly.

A memory entry may contain metadata such as:

```text
ID
Aliases
Description
Related
frequency
last_used
```

`Metadata.id` is treated as the authoritative logical identity of a memory entry.

---

## Retrieval

The current retrieval system supports:

- exact ID lookup,
- alias lookup,
- keyword search,
- ranked retrieval,
- Related-memory expansion.

For example, retrieving a variable may also surface related resources or standards.

The current implementation intentionally remains lightweight and does not require a vector database.

---

## Governed Mutation

Persistent memory changes are represented as proposals.

A proposal moves through explicit states rather than directly modifying trusted memory.

Conceptually:

```text
pending
   ↓
approved
   ↓
applied
```

Rejected, pending, or already-applied proposals cannot be applied as new trusted-memory mutations.

The controlled writer derives mutations from validated approved proposals rather than accepting arbitrary filesystem mutation plans.

---

## History and Recovery

Before trusted memory is changed, OuterMemory records a prepared history event and stores the minimal affected pre-state.

Mutation events can transition through states such as:

```text
prepared
applied
recovered
recovery_required
rolled_back
```

If a mutation fails after partially changing memory, OuterMemory attempts to restore the previous state.

If restoration cannot be completed safely, the event can enter `recovery_required`. When that state can be persisted, it blocks further governed mutations until the condition is resolved.

---

## Safety Boundary

OuterMemory currently uses a **capability-based application boundary**.

The AI-facing interface is not given capabilities for:

- approving proposals,
- rejecting proposals,
- initiating rollback,
- arbitrary trusted-memory mutation,
- generic snapshot restoration.

Human-facing operations control approval, rejection, and rollback.

This is an application-level governance model for a local prototype.

OuterMemory does **not** attempt to defend against a malicious process that already has arbitrary Python execution or unrestricted filesystem access.

---

## Current Status

### Implemented

- [x] Markdown-based trusted memory
- [x] Memory parsing and loading
- [x] ID and alias lookup
- [x] Keyword and ranked retrieval
- [x] Related-memory expansion
- [x] Persistent proposal records
- [x] Human approval / rejection boundary
- [x] Controlled trusted-memory mutation
- [x] Minimal pre-mutation snapshots
- [x] History events
- [x] Rollback
- [x] Path and identifier validation
- [x] Best-effort failure recovery and recovery-required blocking
- [x] Recovery-required mutation blocking
- [x] Automated governance tests

Current governed-mutation test suite:

```text
Ran 18 tests
OK
```

### Planned / Experimental

The following ideas are part of the direction of OuterMemory but are **not yet implemented as complete features**:

- [ ] AI-initiated memory retrieval
- [ ] External Knowledge layer
- [ ] Web / documentation / repository retrieval integration
- [ ] Evidence accumulation for memory candidates
- [ ] AI-generated admission proposals
- [ ] Memory audit and maintenance
- [ ] Improved usage statistics
- [ ] Developer-tool / editor integration

---

## Repository Structure

```text
OuterMemory/
├── docs/
│   └── architecture.md
│
├── memory/
│   ├── variables/
│   ├── resources/
│   └── standards/
│
├── history/
│   └── snapshots/
│
├── src/
│   ├── history_manager.py
│   ├── main.py
│   ├── memory_loader.py
│   ├── memory_parser.py
│   ├── memory_query.py
│   ├── memory_retriever.py
│   ├── memory_schema.py
│   ├── memory_writer.py
│   ├── proposal_store.py
│   └── repository_paths.py
│
└── tests/
```

---

## Design Direction

OuterMemory is being developed around a simple distinction:

```text
Information the AI can use
            ≠
Information the system should remember forever
```

Future external retrieval should remain broad.

In a future external-retrieval architecture, information discovered from the web, repositories, documentation, papers, or other sources could participate in reasoning without automatically becoming trusted memory.

Promotion into trusted long-term memory follows a different path:

```text
External Knowledge
        ↓
Repeated usefulness / evidence
        ↓
Proposal
        ↓
Human Review
     ↙       ↘
 Reject     Approve
               ↓
        Trusted Memory
```

The goal is not to limit what an AI can learn.

The goal is to make persistent project knowledge **stable, inspectable, and human-governed**.

---

## Project Stage

OuterMemory is currently an early local prototype.

The focus is on establishing the memory architecture and governance model before adding larger integrations such as external retrieval systems, editor extensions, or autonomous agent workflows.

## Notice

This project was developed with the assistance of AI coding tools, including ChatGPT.

The architecture, design decisions, and key logic of OuterMemory were determined by the author. AI tools were used to assist with implementation, code review, debugging, documentation, and development workflows.

The author remains responsible for the final code, design decisions, and correctness of the project.

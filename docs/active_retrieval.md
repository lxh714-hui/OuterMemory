# Active Retrieval v1

This is an AI-agnostic integration contract for agents using OuterMemory. It does not change OuterMemory Core or cause automatic retrieval; the integrating agent decides when to retrieve.

| Information need | Route |
| --- | --- |
| Persistent project context | OuterMemory retrieval |
| Current repository/source-code facts | Repository inspection |
| General programming knowledge | Model knowledge |

Use OuterMemory when a task may depend on prior project decisions, conventions or standards, project-specific variables/resources/terminology, previous implementation choices, relationships between trusted entries, or established project context. Do not require it for casual conversation, general programming questions, or work clearly independent of this context.

OuterMemory does not replace source-code inspection. If trusted memory is insufficient for current implementation details, inspect the repository after retrieval. Retrieval is broad and read-oriented; trusted-memory persistence remains separately human-governed.

Codex is the currently validated integration. Other agents can follow this contract through their own integrations.

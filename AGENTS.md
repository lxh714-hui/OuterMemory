# OuterMemory retrieval policy

Follow [the Active Retrieval policy](docs/active_retrieval.md).

When project-specific persistent context is relevant, call `outermemory_retrieve` before manually reading `memory/` files. Inspect the repository directly for current code facts; do not retrieve on every request. Retrieval never authorizes trusted-memory mutation.


from pathlib import Path
import re

from memory_schema import MemorySchema
from memory_parser import MemoryParser
from repository_paths import repository_root


class MemoryValidationError(Exception):
    pass


class DuplicateMemoryIdError(MemoryValidationError):
    pass


MEMORY_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def validate_memory_id(memory_id):
    if not isinstance(memory_id, str) or not MEMORY_ID_PATTERN.fullmatch(memory_id):
        raise MemoryValidationError("invalid logical memory id")
    return memory_id


class MemoryLoader:
    def __init__(self, memory_root=None, repository_root_path=None):
        root = repository_root(repository_root_path)
        self.memory_root = Path(memory_root).resolve() if memory_root else root / "memory"

    def load(self):
        if not self.memory_root.is_dir():
            raise MemoryValidationError(f"memory root does not exist: {self.memory_root}")

        memory = {category: {} for category in MemorySchema.CATEGORIES}
        ids = {}

        for file in self.memory_root.rglob("*.md"):
            relative_path = file.relative_to(self.memory_root)
            if len(relative_path.parts) < 2:
                raise MemoryValidationError(
                    f"memory file must be inside a category: {relative_path}"
                )
            category = relative_path.parts[0]
            if category not in memory:
                raise MemoryValidationError(f"unknown memory category: {category}")

            content = file.read_text(encoding="utf-8")
            parsed = MemoryParser.parse(content)
            metadata = parsed.get("Metadata", {})
            if not content.strip() or not isinstance(metadata, dict) or not metadata.get("id"):
                raise MemoryValidationError(f"invalid memory record: {relative_path}")

            memory_id = metadata["id"]
            validate_memory_id(memory_id)
            if memory_id in ids:
                raise DuplicateMemoryIdError(
                    f"duplicate memory id {memory_id}: {ids[memory_id]} and {relative_path}"
                )
            ids[memory_id] = relative_path
            try:
                frequency = int(metadata.get("frequency", 0))
            except ValueError as error:
                raise MemoryValidationError(f"invalid frequency in {relative_path}") from error

            memory[category][memory_id] = {
                "id": memory_id,
                "frequency": frequency,
                "last_used": metadata.get("last_used", ""),
                "filename": file.name,
                "path": relative_path.as_posix(),
                "category": category,
                "data": parsed,
            }

        return memory

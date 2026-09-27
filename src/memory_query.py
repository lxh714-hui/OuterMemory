import re


# Tokens retain identifier/alias punctuation that has lexical meaning (``_`` and
# ``-``), while punctuation such as commas and slashes separates terms.
TOKEN_PATTERN = re.compile(r"[\w]+(?:[-'][\w]+)*", re.UNICODE)


def tokenize_query(question):
    """Return normalized lexical query tokens without semantic rewriting."""
    if not isinstance(question, str):
        return []
    return [token.casefold() for token in TOKEN_PATTERN.findall(question)]


class MemoryQuery:
    """Deterministic lexical search over ID, Aliases, and Description only.

    Ranking is strongest single evidence for any normalized query token:
    exact ID (11) > exact alias (6) > lexical ID (4) > lexical alias (3)
    > Description lexical match (1). Frequency and other metadata do not affect
    relevance. Equal scores are ordered by logical memory ID.
    """

    def __init__(self, memory):
        self.memory = memory

    def find_by_id(self, memory_id):
        for category in self.memory.values():
            if memory_id in category:
                return category[memory_id]
        return None

    def find_by_alias(self, alias):
        alias = alias.casefold()
        results = []
        for category in self.memory.values():
            for item in category.values():
                aliases = item["data"].get("Aliases", [])
                if alias in [value.casefold() for value in aliases]:
                    results.append(item)
        return results

    def search(self, keyword):
        """Return records having any lexical match in the explicit field policy."""
        return [result["item"] for result in self.search_ranked(keyword)]

    def search_ranked(self, keyword):
        return self.search_ranked_tokens(tokenize_query(keyword))

    def search_ranked_tokens(self, tokens):
        """Rank records using normalized lexical tokens and explicit evidence tiers."""
        tokens = [token for token in tokens if token]
        if not tokens:
            return []

        results = []
        for category in self.memory.values():
            for item in category.values():
                score = self._score(item, tokens)
                if score:
                    results.append({"score": score, "item": item})

        results.sort(key=lambda result: (-result["score"], result["item"]["id"]))
        return results

    def topk(self, keyword, k=5):
        return self.search_ranked(keyword)[:k]

    @staticmethod
    def _score(item, tokens):
        memory_id = item["id"].casefold()
        aliases = [alias.casefold() for alias in item["data"].get("Aliases", [])]
        description = item["data"].get("Description", "").casefold()
        score = 0

        for token in tokens:
            if token == memory_id:
                score = max(score, 11)
            elif token in memory_id:
                score = max(score, 4)

            if token in aliases:
                score = max(score, 6)
            elif any(token in alias for alias in aliases):
                score = max(score, 3)

            if token in description:
                score = max(score, 1)

        return score

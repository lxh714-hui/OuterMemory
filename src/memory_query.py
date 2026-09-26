class MemoryQuery:

    def __init__(self, memory):

        self.memory = memory

    def find_by_id(self, memory_id):

        for category in self.memory.values():

            if memory_id in category:
                return category[memory_id]

        return None

    def find_by_alias(self, alias):

        alias = alias.lower()

        results = []

        for category in self.memory.values():

            for item in category.values():

                aliases = item["data"].get(
                    "Aliases",
                    []
                )

                aliases = [
                    a.lower()
                    for a in aliases
                ]

                if alias in aliases:

                    results.append(item)

        return results

    def search(self, keyword):

        keyword = keyword.lower()

        results = []

        for category in self.memory.values():

            for item in category.values():

                description = (
                    item["data"]
                    .get("Description", "")
                )

                aliases = (
                    item["data"]
                    .get("Aliases", [])
                )

                search_text = (
                    item["id"]
                    + " "
                    + description
                    + " "
                    + " ".join(aliases)
                ).lower()

                if keyword in search_text:

                    results.append(item)

        return results

    def search_ranked(self, keyword):

        keyword = keyword.lower()

        results = []

        for category in self.memory.values():

            for item in category.values():

                score = 0

                description = (
                    item["data"]
                    .get("Description", "")
                )

                aliases = (
                    item["data"]
                    .get("Aliases", [])
                )

                aliases_lower = [
                    a.lower()
                    for a in aliases
                ]

                search_text = (
                    item["id"]
                    + " "
                    + description
                    + " "
                    + " ".join(aliases)
                ).lower()

                # ID精确匹配
                if keyword == item["id"].lower():
                    score += 10

                # Alias匹配
                if keyword in aliases_lower:
                    score += 5

                # 全文匹配
                if keyword in search_text:
                    score += 1

                # Frequency加权
                score += min(
                    item["frequency"],
                    5
                )

                if score > 0:

                    results.append({

                        "score": score,

                        "item": item

                    })

        results.sort(

            key=lambda x: x["score"],

            reverse=True

        )

        return results

    def topk(self, keyword, k=5):

        results = self.search_ranked(
            keyword
        )

        return results[:k]
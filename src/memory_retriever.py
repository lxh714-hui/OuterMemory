from memory_query import MemoryQuery


class MemoryRetriever:

    def __init__(self, memory):

        self.memory = memory

        self.query = MemoryQuery(
            memory
        )

    def deduplicate(self, results):

        unique = {}

        for result in results:

            memory_id = result["item"]["id"]

            if memory_id not in unique:

                unique[memory_id] = result

            elif (
                result["score"]
                >
                unique[memory_id]["score"]
            ):

                unique[memory_id] = result

        return list(
            unique.values()
        )

    def expand_relations(self, results):

        expanded = list(results)

        seen = {
            r["item"]["id"]
            for r in results
        }

        for result in results:

            item = result["item"]

            related = (
                item["data"]
                .get("Related", [])
            )

            for related_id in related:

                if related_id in seen:
                    continue

                related_item = (
                    self.query.find_by_id(
                        related_id
                    )
                )

                if related_item:

                    expanded.append({

                        "score":
                        result["score"] - 1,

                        "item":
                        related_item

                    })

                    seen.add(related_id)

        return expanded

    def retrieve(
        self,
        question,
        topk=5
    ):

        words = question.split()

        results = []

        per_word_k = max(topk, 3)

        for word in words:

            results.extend(

                self.query.topk(
                    word,
                    per_word_k
                )

            )

        results = self.expand_relations(
            results
        )

        results = self.deduplicate(
            results
        )

        results.sort(

            key=lambda x: x["score"],

            reverse=True

        )

        return results[:topk]
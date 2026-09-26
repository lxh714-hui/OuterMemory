class MemoryParser:

    @staticmethod
    def parse(content: str):

        sections = {}

        current_section = None
        buffer = []

        for line in content.splitlines():

            line = line.rstrip()

            if line.startswith("# "):

                if current_section:
                    sections[current_section] = (
                        "\n".join(buffer).strip()
                    )

                current_section = line[2:].strip()
                buffer = []

            else:
                buffer.append(line)

        if current_section:
            sections[current_section] = (
                "\n".join(buffer).strip()
            )

        return MemoryParser._parse_sections(
            sections
        )

    @staticmethod
    def _parse_sections(sections):

        result = {}

        for name, text in sections.items():

            if name == "Metadata":

                result[name] = (
                    MemoryParser._parse_metadata(
                        text
                    )
                )

            elif text.startswith("- "):

                result[name] = (
                    MemoryParser._parse_list(
                        text
                    )
                )

            else:

                result[name] = text

        return result

    @staticmethod
    def _parse_metadata(text):

        data = {}

        for line in text.splitlines():

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            data[key.strip()] = (
                value.strip()
            )

        return data

    @staticmethod
    def _parse_list(text):

        items = []

        for line in text.splitlines():

            line = line.strip()

            if line.startswith("- "):

                items.append(
                    line[2:]
                )

        return items
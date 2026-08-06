from cli.formatter import format_report  # deliberately missing module — build/import failure


def generate_report(results: dict) -> str:
    return format_report(results)

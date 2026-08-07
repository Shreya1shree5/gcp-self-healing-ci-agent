def format_report(results: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in results.items())

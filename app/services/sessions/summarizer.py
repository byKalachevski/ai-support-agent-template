def summarize_messages(messages: list[dict], max_items: int = 8) -> str:
    tail = messages[-max_items:]
    lines = []
    for item in tail:
        role = item.get("role", "unknown")
        text = item.get("text", "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


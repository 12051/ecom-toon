def count_tokens_estimate(text: str) -> int:
    return max(1, len(text) // 4)

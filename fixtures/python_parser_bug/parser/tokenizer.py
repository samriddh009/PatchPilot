"""Tokenizer implementation with string escape handling."""


def tokenize_escaped_string(text: str) -> list[str]:
    """
    Tokenize an escaped character sequence into character tokens.
    Escaped quotes (\" ) should be preserved.
    """
    tokens = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            # DEFECT: drops escaped quotes
            if next_char == '"':
                i += 2
                continue
            tokens.append(next_char)
            i += 2
            continue
        tokens.append(char)
        i += 1
    return tokens

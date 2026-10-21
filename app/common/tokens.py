import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count(text: str) -> int:
    return len(_enc.encode(text))

import os

_WORD_SET = None

def load_dictionary():
    global _WORD_SET
    if _WORD_SET is not None:
        return _WORD_SET

    path = os.path.join(os.path.dirname(__file__), 'words.txt')
    with open(path, 'r') as f:
        _WORD_SET = set(word.strip().lower() for word in f if word.strip())

    print(f"[dictionary] loaded {len(_WORD_SET):,} words")
    return _WORD_SET


def is_valid_word(word: str) -> bool:
    return word.lower() in load_dictionary()
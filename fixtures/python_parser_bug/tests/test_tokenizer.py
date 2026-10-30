"""Tokenizer unit and regression tests."""

from parser.tokenizer import tokenize_escaped_string


def test_escaped_quote_handling():
    """Target test: Escaped quote must be preserved as escaped character token."""
    res = tokenize_escaped_string('foo\\"bar')
    assert '"' in res


def test_plain_string():
    """Regression test: Plain string tokenization."""
    assert tokenize_escaped_string("abc") == ["a", "b", "c"]


def test_empty_string():
    """Regression test: Empty string tokenization."""
    assert tokenize_escaped_string("") == []


def test_simple_escape():
    """Regression test: Standard escape sequence."""
    assert tokenize_escaped_string("\\n") == ["n"]


def test_multiple_tokens():
    """Regression test: Multiple characters with escapes."""
    tokens = tokenize_escaped_string("hello")
    assert len(tokens) == 5

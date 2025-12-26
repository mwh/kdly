# Copyright 2025 Michael Homer. See LICENSE for details.
import re
from dataclasses import dataclass
from . import lexer

@dataclass
class Token:
    "A token in KDL source."
    line : int
    column : int


class ValueToken(Token):
    pass


@dataclass
class StringToken(ValueToken):
    value : str


@dataclass
class NumberToken(ValueToken):
    value : int | float

    @staticmethod
    def from_match(match: re.Match, line, column):
        if not match.group('fractional') and not match.group('exponentvalue'):
            return NumberToken(line, column, int(match.group(0)))
        else:
            return NumberToken(line, column, float(match.group(0)))


@dataclass
class LBraceToken(Token):
    pass


@dataclass
class RBraceToken(Token):
    pass


@dataclass
class NewlineToken(Token):
    pass


@dataclass
class SemicolonToken(Token):
    pass


@dataclass
class EqualsToken(Token):
    pass


@dataclass
class LParenToken(Token):
    pass


@dataclass
class RParenToken(Token):
    pass


@dataclass
class KeywordToken(ValueToken):
    value : str


@dataclass
class TagToken(Token):
    value : str


@dataclass
class SuffixTagToken(Token):
    value : str
    def __init__(self, line: int, column: int, value: str):
        if lexer.experimental_suffix_type_annotations:
            super().__init__(line, column)
            self.value = value
        else:
            raise lexer.KDLSyntaxError(f"Illegal use of experimental suffix type annotation feature: suffix type annotations are only a proposed specification feature of KDL at {line}:{column}")


@dataclass
class SlashdashToken(Token):
    pass

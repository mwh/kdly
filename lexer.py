# Copyright 2025 Michael Homer. See LICENSE for details.
import re

from .tokens import *

# This can be set to true to permit `5%`, `10px`, `0x20#apple` posfix type annotations from spec PR #513.
experimental_suffix_type_annotations = False

non_identifier_pattern = re.compile(r'[\\/(){};\[\]"#=]')


def valid_bare_identifier_character(c: str) -> bool:
    """Check if a character is valid in a bare identifier."""
    if c.isspace():
        return False
    if c == '\n':
        return True
    if c in '\\/(){};[]"#=':
        return False
    try:
        validate_character(c, -1, -1)
    except KDLSyntaxError:
        return False
    return True


def valid_bare_identifier(value: str) -> bool:
    """
    Check a full string for validity as a bare identifier.

    This rules out invalid characters, reserved names, and confusables.
    """
    if len(value) == 0:
        return False
    if value[0].isdigit():
        return False
    # Leading sign followed by a digit is not allowed
    if len(value) > 1:
        if value[0] in '-+':
            if value[1].isdigit():
                return False
    # Reserved keyword-like identifiers
    if value == 'nan' or value == 'inf' or value == '-inf' or value == '+inf' or value == 'true' or value == 'false' or value == 'null':
        return False
    for c in value:
        if not valid_bare_identifier_character(c):
            return False
    return True


def handle_escape_sequence(chars: str) -> str:
    """
    Given the sequence part of the escape (i.e. after the backslash), return the corresponding
    replacement string.
    
    Raises a syntax error if the escape sequence is not a valid KDL escape.
    :param chars: The sequence part of the escape (i.e. after the backslash).
    :return: The corresponding replacement string.
    """
    match chars:
        case 'n':
            return '\n'
        case 'r':
            return '\r'
        case 't':
            return '\t'
        case '\\':
            return '\\'
        case '"':
            return '"'
        case 'b':
            return '\b'
        case 'f':
            return '\f'
        case 's':
            return ' '
    if (chars.isspace() and len(chars) == 1 and chars != '\n'):
        return ''
    if chars.startswith('u{'):
        hex_digits = chars[2:-1]
        if len(hex_digits) == 0 or len(hex_digits) > 6 or not all(c in '0123456789abcdefABCDEF' for c in hex_digits):
            raise KDLSyntaxError(f"Invalid Unicode escape sequence: \\{chars}")
        code_point = int(hex_digits, 16)
        return chr(code_point)
    raise KDLSyntaxError(f"Invalid string escape sequence: \\{chars}")


def validate_character(char: str, line: int, column: int):
    """
    Assert that character is permitted to appear in KDL source.
    """
    codepoint = ord(char)
    if codepoint < 0x08 or 0x000e <= codepoint <= 0x001f or codepoint == 0x007f:
        raise KDLSyntaxError(f"Invalid control character at {line}:{column}")
    if 0x200E <= codepoint <= 0x200F or 0x202A <= codepoint <= 0x202E or 0x2066 <= codepoint <= 0x2069:
        raise KDLSyntaxError(f"Invalid formatting character at {line}:{column}")


def lex_explicit_suffix(source: str, index: int, tokens: list[Token], line: int, column: int) -> int:
    """
    Lex an explicit suffix type annotation after a number.
    Assumes that the current character at source[index] is '#'.
    Appends the appropriate StringToken to tokens.
    Returns the updated index after lexing the suffix.
    """
    start = index
    index += 1  # skip '#'
    if index >= len(source):
        raise KDLSyntaxError(f"Unexpected end of input after '#' at {line}:{column}")
    if source[index].isspace() or source[index] in '\\/){};[]=':
        raise KDLSyntaxError(f"Expected type identifier after '#' at {line}:{column}")
    if source[index] == '"':
        raise KDLSyntaxError(f"Expected bare identifier after '#' at {line}:{column}, got quoted string")
    while index < len(source) and not (source[index].isspace() or non_identifier_pattern.match(source[index])):
        validate_character(source[index], line, column + (index - start))
        index += 1
    identifier = source[start + 1:index]
    if not valid_bare_identifier(identifier):
        raise KDLSyntaxError(f"Invalid identifier in explicit suffix type annotation: '{identifier}' at {line}:{column}")
    tokens.append(SuffixTagToken(line, column + 1, identifier))
    return index


def tokenise(source: str) -> list[Token]:
    """
    Produce a list of tokens.Token from a string.
    
    Will raise KDLSyntaxError at this point if the source is
    lexically invalid (e.g. contains an illegal character).
    """
    line = 1
    column = 0
    decimal_pattern = re.compile(r'(?P<sign>[-+])?(?P<whole>[0-9_]+)(\.(?P<fractional>[0-9_]+))?([eE](?P<exponentsign>[-+])?(?P<exponentvalue>[0-9_]+))?')
    hex_pattern = re.compile(r'0x(?P<full>(?P<sign>[-+])?(?P<whole>(_*[A-Fa-f0-9])+))_*')
    octal_pattern = re.compile(r'0o(?P<full>(?P<sign>[-+])?(?P<whole>(_*[0-7])+))_*')
    binary_pattern = re.compile(r'0b(?P<full>(?P<sign>[-+])?(?P<whole>(_*[01])+))_*')
    raw_multiline_string_pattern = re.compile(r'(#+)"""')
    raw_string_pattern = re.compile(r'(#+)"')
    single_line_comment_pattern = re.compile(r'//[^\n]*')
    keyword_pattern = re.compile(r'inf|-inf|nan|true|false|null')
    line_pattern = re.compile(r'^.*$', re.MULTILINE)
    tokens = []
    index = 0
    mode = None
    line_start = 0
    if source.startswith('\ufeff'):
        index += 1  # skip BOM
    ready = True
    while index < len(source):
        column = index - line_start
        char = source[index]
        if not ready:
            if char.isspace() or char in '\\/){};[]=':
                pass
            else:
                raise KDLSyntaxError(f"Expected whitespace after value at {line}:{column}")
        codepoint = ord(char)
        validate_character(char, line, column)
        if source.startswith('\r\n', index):
            index += 1
            char = '\n'
        if char == '\n' or char in '\u0085\u000a\u000b\u000c\u2028\u2029':
            line += 1
            column = 0
            line_start = index
            index += 1
            tokens.append(NewlineToken(line, column))
            ready = True
            continue
        if char == '\\':
            # line-continuation
            # Just skip this character and the following newline
            index += 1
            inComment = False
            while index < len(source) and source[index].isspace() or inComment or source.startswith('//', index):
                if source.startswith('//', index):
                    inComment = True
                if source[index] == '\n':
                    line += 1
                    column = 0
                    line_start = index
                    index += 1
                    break
                index += 1
            continue
        elif char == '\ufeff':
            # BOM in middle of file
            raise KDLSyntaxError(f"Unexpected BOM character at {line}:{column}")
        elif char.isspace():
            index += 1
            ready = True
            continue
        elif char == '{':
            index += 1
            tokens.append(LBraceToken(line, column))
            ready = True
        elif char == '}':
            index += 1
            tokens.append(RBraceToken(line, column))
            ready = False
        elif char == '#' and (match := keyword_pattern.match(source, index + 1)):
            index = match.end()
            keyword_str = source[match.start():match.end()]
            tokens.append(KeywordToken(line, column, keyword_str))
            ready = False
        elif match := raw_multiline_string_pattern.match(source, index):
            start_line = line
            start_column = column
            marker = match.group(1)
            index = match.end()
            if source[index] != '\n':
                raise KDLSyntaxError(f"Expected newline after opening raw triple-quote at {line}:{column}")
            index += 1
            line += 1
            column = 0
            line_start = index
            start = index
            target = '"""' + marker
            while index < len(source) and not source.startswith(target, index):
                if source[index] == '\n':
                    line += 1
                    column = 0
                    line_start = index
                index += 1
            if index >= len(source):
                raise KDLSyntaxError(f"Unterminated raw multi-line string starting at {line}:{column}")
            string_value = source[start:index]
            index += len(target)
            lines = string_value.split('\n')
            indent = lines.pop()  # last line before closing marker
            for i, ln in enumerate(lines):
                if not ln.startswith(indent):
                    raise KDLSyntaxError(f"Inconsistent indentation in raw multi-line string starting at {start_line}:{start_column}: expected indent {repr(indent)} on line {start_line + i + 1} but got {repr(ln[:len(indent)])}")
            # remove indent from all lines
            string_value = '\n'.join(ln[len(indent):] for ln in lines)            
            tokens.append(StringToken(line, column, string_value))
            ready = False
        elif match := raw_string_pattern.match(source, index):
            marker = match.group(1)
            index = match.end()
            start = index
            target = '"' + marker
            while index < len(source) and not source.startswith(target, index):
                if source[index] == '\n':
                    raise KDLSyntaxError(f"Unterminated string starting at {line}:{column}")
                index += 1
            if index >= len(source):
                raise KDLSyntaxError(f"Unterminated raw string starting at {line}:{column}")
            string_value = source[start:index]
            index += len(target)
            tokens.append(StringToken(line, column, string_value))
            ready = False
        elif char == '=':
            index += 1
            tokens.append(EqualsToken(line, column))
            ready = True
        elif char == ';':
            index += 1
            tokens.append(SemicolonToken(line, column))
            ready = True
        elif char == '(':
            index += 1
            tokens.append(LParenToken(line, column))
            ready = True
        elif char == ')':
            index += 1
            if len(tokens) >= 2 and isinstance(tokens[-2], LParenToken):
                # It's a tag; cheat by popping some tokens off already
                tag_name_token = tokens.pop()
                tokens.pop()  # remove LParenToken
                if not isinstance(tag_name_token, StringToken):
                    raise KDLSyntaxError(f"Invalid type annotation at {line}:{column}")
                tokens.append(TagToken(line, column, tag_name_token.value))
            elif len(tokens) >= 1 and isinstance(tokens[-1], LParenToken):
                raise KDLSyntaxError(f"Empty parentheses at {line}:{column}")
            else:
                # This will be a syntax error later on
                tokens.append(RParenToken(line, column))
            ready = True
        elif match := single_line_comment_pattern.match(source, index):
            # single-line-comment
            # Drop these from the stream entirely.
            index = match.end()
            ready = True
        elif char == '/':
            index += 1
            if index < len(source) and source[index] == '*':
                # multi-line-comment
                index += 1
                target = 1
                while index < len(source):
                    if source[index] == '*' and (index + 1) < len(source) and source[index + 1] == '/':
                        index += 2
                        target -= 1
                        if target == 0:
                            break
                    elif source[index] == '/' and (index + 1) < len(source) and source[index + 1] == '*':
                        target += 1
                        index += 2
                    else:
                        if source[index] == '\n':
                            line += 1
                            column = 0
                            line_start = index
                        index += 1
            elif index < len(source) and source[index] == '-':
                index += 1
                tokens.append(SlashdashToken(line, column))
                ready = True
            else:
                raise KDLSyntaxError(f"Unexpected character '/' at {line}:{column}")
        elif source.startswith('0x', index):
            # hex
            if not (match := hex_pattern.match(source, index)):
                raise KDLSyntaxError(f"Invalid hexadecimal number at {line}:{column}")
            index = match.end()
            number_str = match.group('full')
            tokens.append(NumberToken(line, column, int(number_str, 16)))
            if index < len(source):
                next_char = source[index]
                if next_char == '#':
                    index = lex_explicit_suffix(source, index, tokens, line, column)
                elif not next_char.isspace() and next_char not in ';)}':
                    raise KDLSyntaxError(f"Unexpected character '{next_char}' after number at {line}:{column}")
            ready = False
        elif source.startswith('0o', index):
            # octal
            if not (match := octal_pattern.match(source, index)):
                raise KDLSyntaxError(f"Invalid octal number at {line}:{column}")
            index = match.end()
            number_str = match.group('full')
            tokens.append(NumberToken(line, column, int(number_str, 8)))
            if index < len(source):
                next_char = source[index]
                if next_char == '#':
                    index = lex_explicit_suffix(source, index, tokens, line, column)
                elif not next_char.isspace() and next_char not in ';)}':
                    raise KDLSyntaxError(f"Unexpected character '{next_char}' after number at {line}:{column}")
            ready = False
        elif source.startswith('0b', index):
            # binary
            if not (match := binary_pattern.match(source, index)):
                raise KDLSyntaxError(f"Invalid binary number at {line}:{column}")
            index = match.end()
            number_str = match.group('full')
            tokens.append(NumberToken(line, column, int(number_str, 2)))
            if index < len(source):
                next_char = source[index]
                if next_char == '#':
                    index = lex_explicit_suffix(source, index, tokens, line, column)
                elif not next_char.isspace() and next_char not in ';)}':
                    raise KDLSyntaxError(f"Unexpected character '{next_char}' after number at {line}:{column}")
            ready = False
        elif match := decimal_pattern.match(source, index):
            # decimal
            index = match.end()
            number_str = source[match.start():match.end()]
            tokens.append(NumberToken.from_match(match, line, column))
            if index < len(source):
                next_char = source[index]
                if next_char == '#':
                    index = lex_explicit_suffix(source, index, tokens, line, column)
                elif not next_char.isspace() and next_char not in ';)}':
                    # Possible bare type suffix
                    if not non_identifier_pattern.match(next_char):
                        start = index
                        while index < len(source) and not (source[index].isspace() or non_identifier_pattern.match(source[index])):
                            validate_character(source[index], line, column + (index - start))
                            index += 1
                        identifier = source[start:index]
                        if match.group('exponentvalue'):
                            raise KDLSyntaxError(f"Invalid suffix type annotation on number with exponential part at {line}:{column}")
                        if not valid_bare_identifier(identifier):
                            raise KDLSyntaxError(f"Invalid identifier in suffix type annotation: '{identifier}' at {line}:{column}")
                        if identifier[0] == '.' or identifier[0] == ',':
                            raise KDLSyntaxError(f"Invalid identifier in suffix type annotation: '{identifier}' starts with {identifier[0]} at {line}:{column}")
                        if identifier[0] == 'e' or identifier[0] == 'E':
                            if re.match(r'^[eE][-+]|[eE][0-9]', identifier):
                                raise KDLSyntaxError(f"Invalid identifier in suffix type annotation: '{identifier}' starts with exponential marker at {line}:{column}")
                        tokens.append(SuffixTagToken(line, column + (start - match.start()), identifier))
                        ready = False
                        column = index - line_start
                        if index < len(source):
                            next_char = source[index]
                            if not next_char.isspace() and next_char not in ';)}':
                                raise KDLSyntaxError(f"Unexpected character '{next_char}' after type suffix at {line}:{column}")
                        continue
                    raise KDLSyntaxError(f"Unexpected character '{next_char}' after number at {line}:{column}")
            ready = False
        elif char.isdigit():
            # Error: All legal number values will have been handled by here
            raise KDLSyntaxError(f"Unexpected digit at {line}:{column}")
        elif not non_identifier_pattern.match(char):
            # unambiguous-ident
            start = index
            while index < len(source) and not (source[index].isspace() or non_identifier_pattern.match(source[index])):
                validate_character(source[index], line, column + (index - start))
                index += 1
            identifier = source[start:index]
            if keyword_pattern.fullmatch(identifier):
                raise KDLSyntaxError(f"Invalid identifier string '{identifier}' at {line}:{column}; use '#{identifier}' for keyword values or quote for string.")
            if identifier[0] == '.' and len(identifier) > 1 and identifier[1].isdigit():
                raise KDLSyntaxError(f"Invalid identifier string '{identifier}' at {line}:{column}; identifiers cannot start with a dot followed by a digit.")
            tokens.append(StringToken(line, column, identifier))
            ready = False
        elif source.startswith('"""', index):
            # multi-line-string-start
            start_line = line
            start_column = column
            index += 3
            if source[index:index+1] != '\n':
                raise KDLSyntaxError(f"Expected newline after opening triple-quote at {line}:{column}")
            index += 1
            line += 1
            column = 0
            line_start = index
            # multi-line-string-body
            lines = []
            raw_lines = []
            current_line = ''
            current_line_raw = ''
            while index < len(source):
                c = source[index]
                validate_character(c, line, column + len(current_line_raw))
                current_line_raw += c
                if source.startswith('"""', index):
                    index += 3
                    break
                elif c == '\n':
                    lines.append(current_line)
                    raw_lines.append(current_line_raw)
                    current_line = ''
                    current_line_raw = ''
                    line += 1
                    column = 0
                    line_start = index + 1
                    index += 1
                elif c == '\\':
                    index += 1
                    if index >= len(source):
                        raise KDLSyntaxError(f"Unterminated multi-line string starting at {start_line}:{start_column}")
                    c = source[index]
                    if c.isspace():
                        # skip all whitespace after escape
                        index += 1
                        while index < len(source) and source[index].isspace():
                            if source[index] == '\n':
                                line += 1
                                column = 0
                                line_start = index
                            index += 1
                        c = source[index] if index < len(source) else ''
                        continue
                    if c == 'u':
                        c = source[index:source.index('}', index) + 1]
                        index += len(c) - 1
                    current_line += handle_escape_sequence(c)
                    index += 1
                else:
                    current_line += c
                    index += 1
            indent = current_line
            for ln in raw_lines:
                if not ln.startswith(indent):
                    raise KDLSyntaxError(f"Inconsistent indentation in multi-line string starting at {start_line}:{start_column}: expected indent {repr(indent)} but got {repr(ln[:len(indent)])}")
            # remove indent from all lines
            lines = [ln[len(indent):] for ln in lines]
            tokens.append(StringToken(start_line, start_column, '\n'.join(lines)))
            ready = False
        elif char == '"':
            # quoted-string single-line-string-body
            index += 1
            start = index
            escaped = False
            string_pieces = []
            while index < len(source):
                c = source[index]
                validate_character(c, line, column + (index - start))
                if escaped:
                    if c.isspace():
                        # skip all whitespace after escape
                        index += 1
                        while index < len(source) and source[index].isspace():
                            if source[index] == '\n':
                                line += 1
                                column = 0
                                line_start = index
                            index += 1
                        start = index
                        escaped = False
                        continue
                    if c == 'u':
                        c = source[index:source.index('}', index) + 1]
                        index += len(c) - 1
                    string_pieces.append(handle_escape_sequence(c))
                    escaped = False
                    start = index + 1
                else:
                    if c == '\n':
                        raise KDLSyntaxError(f"Unterminated string starting at {line}:{column}")
                    if c == '\\':
                        escaped = True
                        string_pieces.append(source[start:index])
                    elif c == '"':
                        index += 1
                        string_pieces.append(source[start:index - 1])
                        break
                    else:
                        pass # continue with regular string text
                index += 1
            string_value = ''.join(string_pieces)
            tokens.append(StringToken(line, column, string_value))
            ready = False
        else:
            raise KDLSyntaxError(f"Unexpected character: {char}")    
    tokens.append(NewlineToken(line, column))  # EOF marker
    return tokens


class KDLSyntaxError(Exception):
    """
    Represents a syntax error encountered during KDL lexing or parsing.
    """
    pass

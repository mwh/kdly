# Copyright 2025 Michael Homer. See LICENSE for details.
import typing
from .lexer import tokenise, KDLSyntaxError
from .tokens import *
from .documents import Document, Node


def skip_newlines(tokens, index: int) -> int:
    """
    Skip newline tokens, returning the index of the next non-newline token.
    """
    while index < len(tokens) and isinstance(tokens[index], NewlineToken):
        index += 1
    return index


def skip_terminators(tokens, index: int) -> int:
    """
    Skip tokens that are either newlines or semicolons, returning the index of the next non-terminator token.
    """
    while index < len(tokens) and (isinstance(tokens[index], NewlineToken) or isinstance(tokens[index], SemicolonToken)):
        index += 1
    return index


def parse_value(tokens, index: int) -> tuple[str | int | float | bool | None, str | None, int]:
    """
    Parse a single value starting from either the preceding type annotation or the value token itself.
    Always produces one of the primitive types.
    """
    token = tokens[index]
    type_annotation = None
    if isinstance(token, TagToken):
        type_annotation = token.value
        index += 1
        token = tokens[index]
    next_token = None
    if index + 1 < len(tokens):
        next_token = tokens[index + 1]
    if isinstance(token, StringToken):
        return token.value, type_annotation, index + 1
    elif isinstance(token, NumberToken):
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            if isinstance(next_token, SuffixTagToken):
                if type_annotation:
                    raise KDLSyntaxError(f"Multiple type annotations for value at {next_token.line}:{next_token.column}")
                type_annotation = next_token.value
                index += 1    
        return token.value, type_annotation, index + 1
    elif isinstance(token, KeywordToken):
        if token.value == 'true':
            return True, type_annotation, index + 1
        elif token.value == 'false':
            return False, type_annotation, index + 1
        elif token.value == 'null':
            return None, type_annotation, index + 1
        elif token.value in ('inf', '-inf', 'nan'):
            return float(token.value), type_annotation, index + 1
        raise KDLSyntaxError(f"Unknown keyword value '{token.value}' at {token.line}:{token.column}")
    else:
        raise KDLSyntaxError(f"Expected value at {token.line}:{token.column}, not {type(token)}")


def parse_node(tokens, index: int,
               type_map: dict[str, typing.Callable[[typing.Any], typing.Any]] = {},
               node_map: dict[str, SimpleNodeCallable | typing.Type[Node]] = {}
               ) -> tuple[Node, int]:
    """
    Parse a single node starting from either the preceding type annotation or the node name.
    """
    token = tokens[index]
    node_annotation = None
    if isinstance(token, TagToken):
        node_annotation = token.value
        index += 1
        token = tokens[index]
    if not isinstance(token, StringToken):
        raise KDLSyntaxError(f"Expected node name at {token.line}:{token.column}, not {type(token)}")
    node_name = token.value
    index += 1
    args = []
    args_annotations = []
    properties = {}
    property_annotations = {}
    slashdashed = False
    while isinstance(tokens[index], ValueToken) or isinstance(tokens[index], TagToken) or isinstance(tokens[index], SlashdashToken):
        if isinstance(tokens[index], SlashdashToken):
            slashdashed = True
            index += 1
            index = skip_newlines(tokens, index)
            if index < len(tokens) and isinstance(tokens[index], LBraceToken):
                break
        value, type_annotation,index = parse_value(tokens, index)
        if index < len(tokens):
            if isinstance(tokens[index], EqualsToken) and not type_annotation:
                # property
                property_name = value
                index += 1
                property_value, type_annotation, index = parse_value(tokens, index)
                if not slashdashed:
                    if type_annotation is not None and type_annotation in type_map:
                        property_value = type_map[type_annotation](property_value)
                    properties[property_name] = property_value
                    property_annotations[property_name] = type_annotation
            else:
                # argument
                if not slashdashed:
                    if type_annotation is not None and type_annotation in type_map:
                        value = type_map[type_annotation](value)
                    args.append(value)
                    args_annotations.append(type_annotation)
        elif not slashdashed:
            args.append(value)
        slashdashed = False
        if index >= len(tokens):
            break
    nodes = None
    while index < len(tokens) and isinstance(tokens[index], (LBraceToken, SlashdashToken)):
        children = Document()
        if isinstance(tokens[index], SlashdashToken):
            index += 1
            slashdashed = True
        index = skip_newlines(tokens, index)
        if index < len(tokens) and isinstance(tokens[index], LBraceToken):
            index += 1
            index = skip_newlines(tokens, index)
            while not isinstance(tokens[index], RBraceToken):
                if isinstance(tokens[index], SlashdashToken):
                    index += 1
                    index = skip_newlines(tokens, index)
                    _, index = parse_node(tokens, index, type_map, node_map)
                else:
                    child_node, index = parse_node(tokens, index, type_map, node_map)
                    children.append(child_node)
                if index >= len(tokens):
                    raise KDLSyntaxError(f"Expected '}}' before end of tokens")
                index = skip_terminators(tokens, index)
            index += 1  # skip RBraceToken
        if not slashdashed:
            if nodes is not None:
                raise KDLSyntaxError(f"Multiple child node blocks for node '{node_name}' at {token.line}:{token.column}'")
            nodes = children
        slashdashed = False
    if index < len(tokens):
        token = tokens[index]
        if not (isinstance(token, (NewlineToken, SemicolonToken, RBraceToken))):
            raise KDLSyntaxError(f"Unexpected token after node '{node_name}' at {token.line}:{token.column}: {type(token)}")
    if node_name in node_map:
        node_class = node_map[node_name]
        if isinstance(node_class, type) and issubclass(node_class, Node):
            ret = node_class(node_name, node_annotation, args, properties, nodes if nodes is not None else Document(), args_annotations, property_annotations)
        else:
            ret = node_class(nodes if nodes is not None else Document(), *args, **properties)
    else:
        ret = Node(node_name, node_annotation, args, properties, nodes if nodes is not None else Document(), args_annotations, property_annotations)
    if node_annotation is not None and node_annotation in type_map:
        ret = type_map[node_annotation](ret)
    return ret, index


def parse(source: str,
          type_map: dict[str, typing.Callable[[typing.Any], typing.Any]] = {},
          node_map: dict[str, SimpleNodeCallable | typing.Type[Node]] = {}
          ) -> Document:
    """
    Parse a KDL source string into a Document.
    
    :param source: The KDL source string to parse.
    :param type_map: A mapping of type annotation strings to callables for type conversion during parsing. The callable may either primitive arguments of any type or Node objects, and should return the value to use in place of that value.
    :param node_map: A mapping of node names to either Node subclasses or simpler functions for custom node creation during parsing. The conversion callable should either be a subclass of Node, accepting all the standard Node constructor arguments, or a function accepting a Document of child nodes and then arguments and keyword arguments corresponding to the arguments and parameters of the node.
    :return: The parsed Document object representing the KDL source.
    """
    ret = Document()
    tokens = tokenise(source)
    index = 0
    while index < len(tokens):
        if isinstance(tokens[index], NewlineToken) or isinstance(tokens[index], SemicolonToken):
            index += 1
            continue
        slashdashed = False
        if isinstance(tokens[index], SlashdashToken):
            slashdashed = True
            index += 1
            index = skip_newlines(tokens, index)
        node, index = parse_node(tokens, index, type_map, node_map)
        if not slashdashed:
            ret.append(node)
    return ret


class SimpleNodeCallable(typing.Protocol):
    """
    Type for simple functions taking a document of child nodes, and positional
    arguments for arguments, and keyword arguments for properties. Should
    return a Node object, which can be a subclass, but nothing within kdly
    relies on that.
    """
    def __call__(self, children : Document, *arguments, **properties) -> Node:
        ...

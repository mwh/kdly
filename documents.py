# Copyright 2025 Michael Homer. See LICENSE for details.
import itertools
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from .lexer import valid_bare_identifier

@dataclass
class Document:
    """
    A KDL document, containing an ordered list of Nodes.
    """
    nodes : list[Node] = field(default_factory=list)    
    
    def append(self, node: Node):
        self.nodes.append(node)

    def stringify(self, indent: int = 0,
                  type_map: dict[str, Callable[[Any], str | int | float | bool | None]] = {}) -> str:
        """
        Produce a canonical KDL string representation of this document.

        If type_map is given, it is used to transform values that had a (type) annotation
        in the source document back into their KDL form (i.e. a tagged string/int/float/bool
        value, or a different node).
        """
        ret = ''
        indent_str = ' ' * indent
        for node in self.nodes:
            ret += f"{indent_str}{node.stringify(indent, type_map=type_map)}\n"
        return ret
    
    def __len__(self):
        return len(self.nodes)
    
    def __iter__(self):
        return iter(self.nodes)
    
    def get(self, name: str) -> Node | None:
        """
        Return the first node with the given name, or None if not found.
        """
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    def __getitem__(self, name: str) -> Node:
        """
        Return the first node with the given name, or raise KeyError if not found.
        """
        node = self.get(name)
        if node is None:
            raise KeyError(f"No such node: {name}")
        return node
    
    def __truediv__(self, other: str | tuple[str, ...] | ellipsis) -> NodeCollection:
        """
        Navigate to a collection of nodes by name. If the given name is a tuple,
        all direct child nodes with any of the given names are returned. If it is a
        single string, all nodes with that name are returned.
        
        Passing ellipsis (...) produces an object where the next navigation step
        will operate recursively. For example, in the case of document / ... / "foo",
        all nodes named "foo" at any depth within the document will be produced.
        
        :param other: Name or tuple of names of nodes to select, or ellipsis for recursive selection.
        :return: A possibly-empty collection of nodes, which also supports further navigation.
        """
        if other is ...:
            return NodeCollection(self.nodes, _deep=True)
        if isinstance(other, tuple):
            nodes = [x for x in self.nodes if x.name in other]
        else:
            nodes = [x for x in self.nodes if x.name == other]
        return NodeCollection(nodes)

    def __floordiv__(self, other: str | tuple[str, ...]) -> Node:
        """
        Return the first direct child node with (one of) the given name(s),
        or raise KeyError if none exists..
        
        :param other: Name or tuple of names of nodes to select.
        :type other: str | tuple[str, ...]
        :return: The first node with this name.
        """
        for node in self.nodes:
            if isinstance(other, tuple):
                if node.name in other:
                    return node
            else:
                if node.name == other:
                    return node
        raise KeyError(f"No such node: {other}")
    
    def __contains__(self, item: str) -> bool:
        """
        Returns true if there is a direct child node with this name.
        """
        for node in self.nodes:
            if node.name == item:
                return True
        return False


@dataclass
class Node:
    """
    A KDL node. Has a `name` string, optional type `annotation`, list of positional `args`,
    dictionary of keyword `properties`, and a `children` Document of child nodes.
    
    Annotations on arguments and properties are stored in `arg_annotations` and
    `property_annotations` respectively, while nodes know their own annotations.
    """
    name : str
    annotation : str | None = None
    arguments : list = field(default_factory=list)
    properties : dict = field(default_factory=dict)
    children : Document = field(default_factory=Document)
    argument_annotations : list[str | None] = field(default_factory=list)
    property_annotations : dict[str, str | None] = field(default_factory=dict)

    def stringify(self, indent: int = 0, type_map: dict[str, Callable[[Any], str | int | float | bool | None]] = {}) -> str:
        """
        Produce a canonical KDL string representation of this Node, indented by the given number of spaces.

        If type_map is given, it is used to transform values that had a (type) annotation
        in the source document back into their KDL form (i.e. a tagged string/int/float/bool
        value, or a different node).
        """
        ret = f'({value_to_string(self.annotation)})' if self.annotation is not None else ''
        ret += value_to_string(self.name)
        if self.arguments:
            for arg, annotation in zip(self.arguments, itertools.chain(self.argument_annotations, itertools.repeat(None))):
                ret += ' '
                if annotation is not None:
                    ret += f'({value_to_string(annotation)})'
                ret += value_to_string(arg, annotation=annotation, type_map=type_map)
        for key, value in sorted(self.properties.items(), key=lambda item: item[0]):
            annotation = self.property_annotations.get(key)
            ret += f' {value_to_string(key)}='
            if annotation is not None:
                ret += f'({value_to_string(annotation)})'
            ret += value_to_string(value, annotation=annotation, type_map=type_map)
        if len(self.children):
            ret += ' {\n'
            ret += self.children.stringify(indent + 4, type_map=type_map)
            ret += ' ' * indent + '}'
        return ret

    def get(self, name):
        return self.children.get(name)
    
    def __truediv__(self, other: str | tuple[str, ...] | ellipsis) -> NodeCollection:
        """
        Navigate to a collection of child nodes by name. If the given name is a tuple,
        all direct child nodes with any of the given names are returned. If it is a
        single string, all nodes with that name are returned.

        Passing ellipsis (...) produces an object where the next navigation step
        will operate recursively. For example, in the case of node / ... / "foo",
        all nodes named "foo" at any depth within the node's children will be produced.
        """
        return self.children / other
    
    def __floordiv__(self, other: str | tuple[str, ...]) -> Node:
        """
        Produce the single child node with (one of) the given name(s),
        or raise KeyError if none exists.
        """
        return self.children // other
    
    def __getitem__(self, index : int | str) -> Any:
        """
        Return either the argument at the given index, or the property with the given name,
        depending on the type of index.

        If the requested item does not exist, raises IndexError or KeyError as appropriate.
        
        :param index: If int, the argument index to retrieve. If str, the property name to retrieve.
        :type index: int | str
        :return: A KDL value.
        """
        if isinstance(index, int):
            return self.arguments[index]
        else:
            return self.properties[index]


def value_to_string(value, annotation: str | None = None, type_map: dict[str, Callable[[Any], str | int | float | bool | None]] = {}) -> str:
    """
    Convert a primitive value to its canonical KDL string representation,
    applying type conversion if a type annotation and type_map are given.
    """
    if annotation is not None and annotation in type_map:
        value = type_map[annotation](value)
    if isinstance(value, str):
        if valid_bare_identifier(value):
            return value
        # Escape all escapable characters except space
        escaped = (value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
                   .replace('\r', '\\r').replace('\b', '\\b').replace('\f', '\\f') )
        return f'"{escaped}"'
    elif isinstance(value, bool):
        return f'#{"true" if value else "false"}'
    elif value is None:
        return '#null'
    elif isinstance(value, float):
        if value == float('inf'):
            return '#inf'
        elif value == float('-inf'):
            return '#-inf'
        elif value != value:
            return '#nan'
        return str(value)
    elif isinstance(value, int):
        return str(value)
    return f'<<unsupported value: {value!r}>>'


@dataclass
class NodeCollection:
    """
    A collection of KDL nodes, supporting navigation and selection.
    The collection may be empty. If _deep is True, navigation operations
    on this collection will operate recursively, but that will not propagate
    to further collections produced from it.
    """
    _nodes : list[Node]
    _deep : bool = False

    def stringify(self, indent: int = 0,
                  type_map: dict[str, Callable[[Any], str | int | float | bool | None]] = {}) -> str:
        ret = ''
        indent += 4
        indent_str = ' ' * indent
        ret += 'NodeCollection of ' + str(len(self._nodes)) + ' nodes:\n'
        for node in self._nodes:
            ret += f"{indent_str}{node.stringify(indent, type_map=type_map)}\n"
        return ret

    def __str__(self):
        return self.stringify()
    
    def __iter__(self):
        return iter(self._nodes)
    
    def __truediv__(self, other: str | tuple[str, ...] | ellipsis) -> NodeCollection:
        """
        Navigate to children of the nodes in this collection, by name.
        If the given name is a tuple, all direct child nodes with any of the given names are returned.
        If it is a single string, all nodes with that name are returned.

        Passing ellipsis (...) produces an object where the next navigation step
        will operate recursively (i.e. a NodeCollection with _deep=True).
        For example, in the case of collection / ... / "foo", all nodes named "foo"
        at any depth within any node in the collection will be produced.
        """
        if other is ...:
            return NodeCollection(self._nodes, _deep=True)
        if self._deep:
            nodes = []
            queue = []
            queue.extend(self._nodes)
            while queue:
                node = queue.pop(0)
                queue.extend(node.nodes.nodes)
                if isinstance(other, tuple):
                    if node.name in other:
                        nodes.append(node)
                else:
                    if node.name == other:
                        nodes.append(node)
            return NodeCollection(nodes)
        nodes = [node for x in self._nodes for node in x.children / other]
        return NodeCollection(nodes)
    
    def __floordiv__(self, other: str | tuple[str, ...]) -> Node:
        """
        Produce the first node with (one of) the given name(s) from within
        the children of any node in this collection, or raise KeyError if none exists.
        """
        for node in self._nodes:
            for node2 in node.children:
                if isinstance(other, tuple):
                    if node2.name in other:
                        return node2
                else:
                    if node2.name == other:
                        return node2
        raise KeyError(f"No such node: {other}")
    
    def __add__(self, other: NodeCollection) -> NodeCollection:
        "Combine two NodeCollections into one, concatenating their node lists."
        return NodeCollection(self._nodes + other._nodes)

    def __getitem__(self, index: int | str) -> Any:
        """
        Return a list of either arguments in the given index from all nodes in the collection,
        or properties with the given name from all nodes in the collection, depending on the type of index.

        If the requested item does not exist in all nodes, raises IndexError or KeyError as appropriate.
        
        :param index: If int, the argument index to retrieve. If str, the property name to retrieve.
        :type index: int | str
        :return: A list of KDL values (not nodes).
        """
        if isinstance(index, int):
            ret = []
            for x in self._nodes:
                if len(x.arguments) > index:
                    ret.append(x.arguments[index])
                else:
                    raise IndexError(f"Node '{x.name}' has no argument at index {index}")
        else:
            ret = []
            for node in self._nodes:
                if index in node.properties:
                    ret.append(node.properties[index])
                else:
                    raise KeyError(f"Node '{node.name}' has no property '{index}'")
        return ret
    
    def __len__(self):
        "Number of nodes in this collection."
        return len(self._nodes)
    
    def __contains__(self, item: str) -> bool:
        "Check if any node in the collection has the given name."
        for node in self._nodes:
            if node.name == item:
                return True
        return False

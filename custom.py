# Copyright 2025 Michael Homer. See LICENSE for details.
import annotationlib
import typing
import datetime

from . import documents
from . import parser

type Argument[T] = T
type Child[T] = T
type Properties[T] = T
type OtherChildren = list[BaseNode]


class BaseNodeProto[T : BaseNode](typing.Protocol):
    """
    Protocol for use in node mapping dictionaries, corresponding to constructors of BaseNode subclasses.
    """
    _node_name: typing.ClassVar[str]

    def __call__(self, node_name: str, type_annotation: str | None, children: list[BaseNode], *arguments, **properties) -> T:
        ...


def node_named[T : BaseNode](name: str) -> typing.Callable[[typing.Type[T]], typing.Type[T]]:
    """
    Decorator to override the default node name for a BaseNode subclass. Otherwise, the
    name of the class is used as the node name.
    """
    def decorator(cls: typing.Type[T]) -> typing.Type[T]:
        cls._node_name = name
        return cls
    return decorator


class BaseNode:
    """
    Base class to be inherited by bespoke node implementations.

    Subclasses should define type-annotated attributes for any expected
    positional arguments, properties, and child nodes.
    """
    _node_name: typing.ClassVar[str]

    def __init_subclass__(cls) -> None:
        cls._node_name = cls.__name__

    @classmethod
    def _parse(cls, kdl_source: str) -> list[typing.Self]:
        """
        Parse a KDL source string into a list of nodes created from
        subclasses of this class. Every subclass will be mapped to a node name
        matching its class name, unless overridden with the `@node_named` decorator.
        """
        node_map: dict[str, BaseNodeProto] = {}
        for subclass in cls.__subclasses__():
            node_map[subclass._node_name] = subclass # type: ignore
        doc = parser.parse(kdl_source)
        return [customise_node(node, node_map) for node in doc.nodes]

    def __init__(self, node_name: str, type_annotation: str | None = None, children: list[BaseNode] = [], *arguments, **properties) -> None:
        cls = type(self)
        annotations = annotationlib.get_annotations(cls)
        self._this_node_name = node_name
        self._type_annotation = type_annotation
        self._all_properties = dict(properties)
        self._all_children = list(children)
        self._all_arguments = list(arguments)
        self._argument_names = []
        self._child_attributes = {}

        # Look for attributes meant to hold other nodes
        collect_children = dict()
        other_children = []
        has_child_collector = False
        for name, typ in annotations.items():
            origin = typing.get_origin(typ)
            if isinstance(typ, type) and issubclass(typ, BaseNode):
                collect_children[typ._node_name] = (name, False)
                setattr(self, name, None)
            elif origin is list:
                param = typing.get_args(typ)
                if param and isinstance(param[0], typing.Union):
                    args = typing.get_args(param[0])
                    for arg in args:
                        if isinstance(arg, type) and issubclass(arg, BaseNode):
                            collect_children[arg._node_name] = (name, True)
                            setattr(self, name, [])
                            # break
                elif param and issubclass(param[0], BaseNode):
                    node_name = param[0]._node_name
                    collect_children[node_name] = (name, True)
                    setattr(self, name, [])
                else:
                    pass # Can have ordinary lists as properties.
            elif typ is OtherChildren:
                setattr(self, name, other_children)
                has_child_collector = True
            elif origin is typing.Union:
                args = typing.get_args(typ)
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseNode):
                        collect_children[arg._node_name] = (name, False)
                        setattr(self, name, None)
                        break
        
        # Scan children and put into the right attributes
        for child in children:
            child_node_name = child._this_node_name
            if child_node_name in collect_children:
                attr_name, is_list = collect_children[child_node_name]
                if is_list:
                    getattr(self, attr_name).append(child)
                elif getattr(self, attr_name, None) is not None:
                    raise TypeError(f'Node {cls.__name__} can only have one child of type {child_node_name}')
                else:
                    setattr(self, attr_name, child)
            elif not has_child_collector:
                raise TypeError(f'Node {cls.__name__} cannot have child of type {child_node_name}')
            else:
                other_children.append(child)

        # Now process positional arguments in order
        argument_index = 0
        argument_collector = None
        argument_collector_type = None
        remaining_properties = dict(properties)
        for name, typ in annotations.items():
            origin = typing.get_origin(typ)
            if origin is Argument:
                type_args = typing.get_args(typ)
                if type_args:
                    arg_type = type_args[0]
                    arg_wrapper_origin = typing.get_origin(arg_type)
                    if arg_wrapper_origin and issubclass(arg_wrapper_origin, list):
                        argument_collector = []
                        setattr(self, name, argument_collector)
                        param = typing.get_args(arg_type)
                        if param:
                            argument_collector_type = param[0]
                    else:
                        if arg_type is str and not isinstance(arguments[argument_index], str):
                            raise TypeError(f'Argument {name} at index {argument_index} of {cls.__name__} expected string but got {type(arguments[argument_index]).__name__}')
                        elif arg_type is int and not isinstance(arguments[argument_index], int):
                            raise TypeError(f'Argument {name} at index {argument_index} of {cls.__name__} expected integer but got {type(arguments[argument_index]).__name__}')
                        elif arg_type is bool and not isinstance(arguments[argument_index], bool):
                            raise TypeError(f'Argument {name} at index {argument_index} of {cls.__name__} expected boolean but got {type(arguments[argument_index]).__name__}')
                        elif arg_type is float and not isinstance(arguments[argument_index], float):
                            raise TypeError(f'Argument {name} at index {argument_index} of {cls.__name__} expected float but got {type(arguments[argument_index]).__name__}')
                        elif arg_type not in (str, int, bool, float):
                            if argument_index < len(self._all_arguments):
                                self._all_arguments[argument_index] = convert_value(arguments[argument_index], arg_type)
                            else:
                                continue
                        setattr(self, name, self._all_arguments[argument_index])
                        self._argument_names.append(name)
                        argument_index += 1
                pass
            elif typ is Properties or origin is Properties:
                setattr(self, name, remaining_properties)

        # At end of list, add extra arguments into collector if present
        if argument_collector is not None:
            while argument_index < len(arguments):
                if argument_collector_type is not None:
                    if not compatible_value(arguments[argument_index], argument_collector_type):
                        raise TypeError(f'Argument collector of {cls.__name__} expected items of type {argument_collector_type.__name__} but got {type(arguments[argument_index]).__name__}')
                argument_collector.append(arguments[argument_index])
                argument_index += 1
        else:
            if argument_index < len(arguments):
                raise TypeError(f'Too many positional arguments for {cls.__name__}: expected {argument_index} but got {len(arguments)}')

        # Now process properties
        for name, typ in annotations.items():
            if name in properties:
                value = properties[name]
                expected_type = typ
                if typing.get_origin(typ) is typing.Union:
                    args = typing.get_args(typ)
                    found_compatible = False
                    for arg in args:
                        if compatible_value(value, arg):
                            expected_type = arg
                            found_compatible = True
                            break
                    if not found_compatible:
                        raise TypeError(f'Property {name} of {cls.__name__} expected one of {[a.__name__ for a in args]} but got {type(value).__name__}')
                elif not isinstance(value, expected_type):
                    try:
                        value = convert_value(value, expected_type)
                    except Exception:
                        raise TypeError(f'Property {name} of {cls.__name__} expected {expected_type.__name__} but got {type(value).__name__}')
                setattr(self, name, value)
                del remaining_properties[name]
            elif name in self.__dict__:
                pass  # Already set by argument or child processing
            elif name.startswith('_'):
                pass  # Private attribute, ignore
            else:
                if self.__class__.__dict__.get(name) is not None:
                    setattr(self, name, self.__class__.__dict__[name])
                else:
                    raise TypeError(f'Missing required property {name} of {cls.__name__}')


    def __str__(self) -> str:
        anns = annotationlib.get_annotations(type(self))
        ret = self._this_node_name
        if self._all_arguments:
            for name in self._argument_names:
                value = getattr(self, name)
                ret += ' '
                ret += value_to_string(value)
            for arg in self._all_arguments[len(self._argument_names):]:
                ret += ' '
                ret += value_to_string(arg)

        if self._all_properties:
            for name, typ in anns.items():
                if typ is Properties or typing.get_origin(typ) is Properties:
                    props = getattr(self, name)
                    for key, value in props.items():
                        ret += f' {key}={value_to_string(value)}'
                elif name.startswith('_'):
                    pass
                elif typ is Argument or typing.get_origin(typ) is Argument:
                    pass
                elif typ is OtherChildren:
                    pass
                elif isinstance(typ, type) and issubclass(typ, BaseNode):
                    pass
                elif typing.get_origin(typ) is list:
                    pass
                else:
                    value = getattr(self, name)
                    ret += f' {name}={value_to_string(value)}'
        
        if self._all_children:
            ret += ' {\n'
            for name, typ in anns.items():
                if typ is Properties or typing.get_origin(typ) is Properties:
                    pass
                elif name.startswith('_'):
                    pass
                elif typ is Argument or typing.get_origin(typ) is Argument:
                    pass
                elif typ is OtherChildren:
                    children = getattr(self, name)
                    for child in children:
                        child_str = str(child)
                        child_lines = child_str.splitlines()
                        for line in child_lines:
                            ret += '    ' + line + '\n'
                elif isinstance(typ, type) and issubclass(typ, BaseNode):
                    child = getattr(self, name)
                    if child is not None:
                        child_str = str(child)
                        child_lines = child_str.splitlines()
                        for line in child_lines:
                            ret += '    ' + line + '\n'
                elif typing.get_origin(typ) is list:
                    param = typing.get_args(typ)
                    if param and isinstance(param[0], typing.Union):
                        args = typing.get_args(param[0])
                        has_nodes = False
                        for arg in args:
                            if isinstance(arg, type) and issubclass(arg, BaseNode):
                                has_nodes = True
                                break
                        if has_nodes:
                            children = getattr(self, name)
                            for child in children:
                                child_str = str(child)
                                child_lines = child_str.splitlines()
                                for line in child_lines:
                                    ret += '    ' + line + '\n'
                    elif param and issubclass(param[0], BaseNode):
                        children = getattr(self, name)
                        for child in children:
                            child_str = str(child)
                            child_lines = child_str.splitlines()
                            for line in child_lines:
                                ret += '    ' + line + '\n'
            ret += '}'
        return ret
    

class BaseDocument(BaseNode):
    """
    Base class to be inherited by bespoke document implementations.

    Each subclass should define type-annotated attributes for any expected
    child nodes, and parseDocument will return an instance of the subclass
    with those fields populated appropriately.

    The stringification of the document will include all mentioned child nodes,
    in the order they were defined in this class.
    """
    @classmethod
    def parseDocument(cls, kdl_source: str, parent : typing.Type[BaseNode] | None = None) -> typing.Self:
        node_map: dict[str, BaseNodeProto] = {}
        if parent is None:
            parent = cls._default_nodegroup
        for subclass in parent.__subclasses__():
            node_map[subclass._node_name] = subclass # type: ignore
        doc = parser.parse(kdl_source)
        return cls(cls.__name__, '', [customise_node(node, node_map) for node in doc.nodes])
    
    def __init_subclass__(cls, nodegroup=BaseNode) -> None:
        cls._default_nodegroup = nodegroup
        return super().__init_subclass__()

    def __str__(self) -> str:
        anns = annotationlib.get_annotations(type(self))
        all_children = []
        for name, typ in anns.items():
            if typ is OtherChildren:
                children = getattr(self, name)
                all_children.extend(children)
            elif isinstance(typ, type) and issubclass(typ, BaseNode):
                child = getattr(self, name)
                if child is not None:
                    all_children.append(child)
            elif typing.get_origin(typ) is list:
                param = typing.get_args(typ)
                if param and isinstance(param[0], typing.Union):
                    args = typing.get_args(param[0])
                    has_nodes = False
                    for arg in args:
                        if isinstance(arg, type) and issubclass(arg, BaseNode):
                            has_nodes = True
                            break
                    if has_nodes:
                        children = getattr(self, name)
                        all_children.extend(children)
                elif param and issubclass(param[0], BaseNode):
                    children = getattr(self, name)
                    all_children.extend(children)
        return '\n'.join(str(child) for child in all_children)


class GenericNode(BaseNode):
    """
    Node with no specialisation; holds all arguments, properties, and children
    in generic attributes.
    """
    arguments : Argument[list[typing.Any]]
    properties : Properties[dict[str, typing.Any]]
    children : OtherChildren


def customise_node[T : BaseNode](node: parser.Node, node_map: dict[str, BaseNodeProto[T]], default=None) -> T:
    """
    Map a single base document node from the parser to one defined in this hierarchy.
    If the node's name matches one in the node_map, an instance of that class is created.
    Otherwise, if a default function is provided, it is called with the node to create
    the instance. If no default is provided, a GenericNode is created. Any of these may
    be later rejected if they are not compatible at this point in their surrounding scope.
    
    :param node: Base parser node to be translated
    :type node: parser.Node
    :param node_map: Mapping from node names to constructors of new node types
    :type node_map: dict[str, BaseNodeProto[T]]
    :param default: Function to create a node if no match is found in node_map (or may raise an exception)
    :return: The created node instance
    :rtype: T
    """
    node_name = node.name
    args = node.arguments
    properties = node.properties
    nodes = node.children

    if node_name in node_map:
        node_class = node_map[node_name]
        return node_class(node_name, node.annotation, [ customise_node(child, node_map) for child in nodes], *args, **properties)
    else:
        if default is None:
            bn = GenericNode(node.name, node.annotation, [customise_node(child, node_map) for child in node.children], *node.arguments, **node.properties)
            bn._this_node_name = node.name
            return bn  # type: ignore
        return default(node)


def convert_value(value, to_type):
    """
    Convert a specific KDL value to an expected Python type.
    """
    if to_type is datetime.date:
        if isinstance(value, str):
            return datetime.date.fromisoformat(value)
        else:
            raise TypeError(f'Cannot convert {type(value).__name__} to date')
    elif to_type is datetime.datetime:
        if isinstance(value, str):
            return datetime.datetime.fromisoformat(value)
        else:
            raise TypeError(f'Cannot convert {type(value).__name__} to datetime')
    else:
        raise TypeError(f'Unsupported conversion to type {to_type.__name__}')


def compatible_value(value, to_type):
    """
    Return true if this KDL value will be permitted to be stored in a field of the given type.
    """
    if to_type is typing.Any:
        return True
    if to_type is str:
        return isinstance(value, str)
    elif to_type is int:
        return isinstance(value, int)
    elif to_type is bool:
        return isinstance(value, bool)
    elif to_type is float:
        return isinstance(value, float)
    elif to_type is datetime.date:
        return isinstance(value, str)
    elif to_type is datetime.datetime:
        return isinstance(value, str)
    else:
        return isinstance(value, to_type)


def value_to_string(value: typing.Any) -> str:
    """
    Convert a Python value to a KDL stringified representation.
    """
    if isinstance(value, datetime.date):
        return documents.value_to_string(value.isoformat())
    elif isinstance(value, datetime.datetime):
        return documents.value_to_string(value.isoformat())
    return documents.value_to_string(value)

__all__ = [
    "BaseNode",
    "BaseDocument",
    "node_named",
    "GenericNode",
    "Argument",
    "Child",
    "Properties",
    "OtherChildren",
    ]
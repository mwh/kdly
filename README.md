# kdly, a KDL parser

This is a parser for the [KDL] Document Language, producing document
objects from textual source.

KDL is a document language along the lines of JSON, XML, or YAML
intended to be used for configuration files and the like. This implementation
is intended to comply with the [KDL 2.0 specification][spec].

## Usage

```py3
import kdly
doc = kdly.parse(pathlib.Path("file.kdl").read_text())
for node in doc:
    # name, args, and properties are available as standard Python values
    print(node.name, node.args)

# Navigate the document tree quickly by node name
for link in doc / 'list' / 'li' / 'a':
    # Properties and arguments are available by indexing
    print(link['href'], link[0])

# Or when there's a single instance of a node expected to be present:
pubdate = doc // 'publication-date'
```

Custom type transformers can be specified for values with type annotations
(e.g. `(u8)231`) and also for node names. Type-tag transformers are given the
base KDL value type (int, float, str, bool, None) and can return any kind of
value.

```py3
# Turn `(base64)"aGVsbG8="` into a bytes object
kdly.parse(source, type_map={'base64': lambda x: base64.decodebytes(x.encode())})
# Create an object of the Person class for any node named "person".
kdly.parse(source, node_map={'person': Person})
```

## Custom node types

Custom node and document classes can be created by declaring subclasses of
types from the kdly.custom module and they will be automatically mapped from
KDL documents. Type annotations determine which attributes correspond to
which part of the KDL document and validate its structure.

```py3
from kdly.custom import *
class PlanNodes(BaseNode):    # Base class for this set of custom nodes
    pass

class person(PlanNodes):      # By default, node name is "person"
    name: Argument[str]       # Positional argument; mandatory
    dob: datetime.date        # Property, will be mapped from a string

class address(PlanNodes):
    number : Argument[int]    # Order of appearance in the class declaration
    street : Argument[str]    # determines the order these are expected.

@node_named("building")       # Override node name to "building"
class BuildingNode(PlanNodes):
    name: Argument[str] = ""  # Optional argument with default value
    place: address            # A single child node, because Address subclasses BaseNode
    people: list[person]      # A list will hold all children of this type

class MyDocument(BaseDocument, nodegroup=PlanNodes):
    # nodegroup=PlanNodes tells document to use subclasses of PlanNodes
    # for its interior nodes; can also be specified at parseDocument below.
    buildings: list[BuildingNode]
    nodes: OtherChildren      # Child nodes not mapped to other fields

doc = MyDocument.parseDocument("""
building Office {
    address 123 "Main Street"
    person "Alice" dob="1990-01-01"
    person "Bob" dob="1985-05-23"
}
person "Charlie" dob="2000-12-12"
""")

print(doc)                    # Will print the document above exactly
```

Fields can be accessed and updated as usual:
```py3
print(doc.buildings[0].place.street)  # Prints "Main Street"
doc.buildings[0].people[0].dob = datetime.date(1991, 2, 2)
print(doc.buildings[0].people[0])     # Prints updated person node
```

Additional arguments, properties, or children not accounted for in
the node or document classes will raise errors. There are catch-all
options for each of these:
```py3
class GenericDocument(BaseDocument):
    arguments : Argument[list[typing.Any]]
    properties : Properties[dict[str, typing.Any]]
    children : OtherChildren
```

It is also possible to declare attributes that will collect multiple specific
kinds of node using union types:
```py3
class Repository(BaseNode):
    refs: list[branch | tag]
```
All `branch` and `tag` nodes will be stored in the list in Repository.refs
in order of their appearance in the body of the repository node.


  [KDL]: https://kdl.dev/
  [spec]: https://kdl.dev/spec/

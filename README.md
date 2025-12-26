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

Custom transformers can be specified to use for values with type annotations
(e.g. `(u8)231`) and also for node names. Type-tag transformers are given the
base KDL value type (int, float, str, bool, None) and can return any kind of
value.

Node names can be mapped to subclasses of the Node type, or through transformer
functions taking the children, positional arguments, and keyword arguments
for properties.

```py3
# Turn `(base64)"aGVsbG8="` into a bytes object
kdly.parse(source, type_map={'base64': lambda x: base64.decodebytes(x.encode())})
# Create an object of the Person class for any node named "person".
kdly.parse(source, node_map={'person': Person})
```

If a node has a type annotation with a transformer as well as a node-name mapping,
the type mapping is applied to the result of the name mapping.

  [KDL]: https://kdl.dev/
  [spec]: https://kdl.dev/spec/

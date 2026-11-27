; What TypeScript and JavaScript code looks like to the tree-sitter reader. The TSX
; dialect reads these patterns and then its own, in tsx.scm.

; ---- definitions

; A test is a call that takes its name as a string and its body as a function, which no
; anchor can name. A function defined in a file that holds one is the nearest thing an
; anchor can name, and in any other file it is no test.
(call_expression
  function: [
    (identifier) @_runner
    (member_expression object: (identifier) @_runner)
  ]
  arguments: (arguments
    . [(string) (template_string)]
    [(arrow_function) (function_expression)])
  (#match? @_runner "^(test|it|describe)$")) @test.call

(function_declaration name: (identifier) @name) @definition.function @test.standin
(generator_function_declaration name: (identifier) @name) @definition.function @test.standin
(function_signature name: (identifier) @name) @definition.function
(class_declaration name: (type_identifier) @name) @definition.type
(abstract_class_declaration name: (type_identifier) @name) @definition.type
(interface_declaration name: (type_identifier) @name) @definition.type
(type_alias_declaration name: (type_identifier) @name) @definition.type
(enum_declaration name: (identifier) @name) @definition.type

; A name bound to a function is a function; any other declarator is a variable.
(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression) (generator_function)])) @definition.function @test.standin
(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression) (generator_function)])) @definition.function @test.standin
(lexical_declaration (variable_declarator name: (identifier) @name)) @definition.variable
(variable_declaration (variable_declarator name: (identifier) @name)) @definition.variable

; CommonJS: a name assigned on `exports` or `module.exports` is the module's, and a
; function assigned on a prototype is a method of the function that is its class.
((expression_statement
   (assignment_expression
     left: (member_expression
       object: (identifier) @_exports
       property: (property_identifier) @name)
     right: [(arrow_function) (function_expression) (generator_function)])) @definition.function
 (#eq? @_exports "exports"))
((expression_statement
   (assignment_expression
     left: (member_expression
       object: (member_expression
         object: (identifier) @_module
         property: (property_identifier) @_exports)
       property: (property_identifier) @name)
     right: [(arrow_function) (function_expression) (generator_function)])) @definition.function
 (#eq? @_module "module")
 (#eq? @_exports "exports"))
((expression_statement
   (assignment_expression
     left: (member_expression
       object: (identifier) @_exports
       property: (property_identifier) @name))) @definition.variable
 (#eq? @_exports "exports"))
((expression_statement
   (assignment_expression
     left: (member_expression
       object: (member_expression
         object: (identifier) @_module
         property: (property_identifier) @_exports)
       property: (property_identifier) @name))) @definition.variable
 (#eq? @_module "module")
 (#eq? @_exports "exports"))
((expression_statement
   (assignment_expression
     left: (member_expression
       object: (member_expression
         object: (identifier) @holder
         property: (property_identifier) @_prototype)
       property: (property_identifier) @name)
     right: [(arrow_function) (function_expression) (generator_function)])) @definition.function
 (#eq? @_prototype "prototype"))

; The members of a class.
(method_definition
  name: [(property_identifier) (private_property_identifier)] @name) @definition.function
(abstract_method_signature name: (property_identifier) @name) @definition.function
(class_body
  (method_signature name: (property_identifier) @name) @definition.function)
(public_field_definition
  name: [(property_identifier) (private_property_identifier)] @name
  value: [(arrow_function) (function_expression)]) @definition.function
(public_field_definition
  name: [(property_identifier) (private_property_identifier)] @name) @definition.variable

; The members of an interface, of the object type an alias names, and of an enum.
(interface_body
  (method_signature name: (property_identifier) @name) @definition.function)
(interface_body
  (property_signature name: (property_identifier) @name) @definition.variable)
(type_alias_declaration
  value: (object_type
    (method_signature name: (property_identifier) @name) @definition.function))
(type_alias_declaration
  value: (object_type
    (property_signature name: (property_identifier) @name) @definition.variable))
(enum_body (property_identifier) @name @definition.variable)
(enum_body (enum_assignment name: (property_identifier) @name) @definition.variable)

; What may stand between a member and its type without hiding it. A block, an object
; literal and a namespace's body are not here, so what they hold is out of reach.
(class_body) @container
(interface_body) @container
(object_type) @container
(enum_body) @container

; `export` and `declare` are part of the definition they introduce.
(export_statement) @wrapper
(ambient_declaration) @wrapper

; A decorator, and each signature of an overload, which belongs to the definition of
; the same name below it, exported or declared as that one is.
(decorator) @decoration
(function_signature) @decoration
(ambient_declaration (function_signature)) @decoration
(export_statement declaration: (function_signature)) @decoration
(export_statement
  declaration: (ambient_declaration (function_signature))) @decoration
(class_body (method_signature) @decoration)

; ---- imports

(import_statement source: (string)) @import
(import_statement (import_require_clause source: (string))) @import
(export_statement source: (string)) @import
((call_expression
   function: (identifier) @_function
   arguments: (arguments . (string) .)) @import
 (#eq? @_function "require"))
(call_expression function: (import) arguments: (arguments . (string))) @import

; ---- references

(identifier) @reference
(type_identifier) @reference
(shorthand_property_identifier) @reference
(member_expression
  object: (_) @access.object
  property: (property_identifier) @access.name) @access

(variable_declarator name: (identifier) @bound)
(shorthand_property_identifier_pattern) @bound
(pair_pattern value: (identifier) @bound)
(array_pattern (identifier) @bound)
(rest_pattern (identifier) @bound)
(required_parameter pattern: (identifier) @bound)
(optional_parameter pattern: (identifier) @bound)
(arrow_function parameter: (identifier) @bound)
(function_declaration name: (identifier) @bound)
(class_declaration name: (type_identifier) @bound)
(catch_clause parameter: (identifier) @bound)
(for_in_statement left: (identifier) @bound)

; ---- canonical text

; A formatter chooses these: the semicolon that ends a statement, which quote a string
; is written in, and the parentheses around an expression it wraps over lines.
";" @layout
(string ["\"" "'"] @layout)
(parenthesized_expression) @transparent

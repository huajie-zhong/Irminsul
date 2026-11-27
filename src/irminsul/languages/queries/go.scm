; What Go code looks like to the tree-sitter reader.

; ---- definitions

(function_declaration name: (identifier) @name) @definition.function

; A method is held by its receiver's type, which does not enclose it.
(method_declaration
  receiver: (parameter_list
    (parameter_declaration
      type: [
        (type_identifier) @holder
        (generic_type type: (type_identifier) @holder)
        (pointer_type (type_identifier) @holder)
        (pointer_type (generic_type type: (type_identifier) @holder))
      ]))
  name: (field_identifier) @name) @definition.function

(type_spec name: (type_identifier) @name) @definition.type
(type_alias name: (type_identifier) @name) @definition.type
(var_spec name: (identifier) @name) @definition.variable
(const_spec name: (identifier) @name value: (_)) @definition.variable

; A constant with no value repeats the expression of the one above it, so a constant
; added or removed above changes what it is: it is its whole block.
(const_declaration (const_spec name: (identifier) @name !value)) @definition.variable

; The fields of a struct and the methods of an interface.
(field_declaration name: (field_identifier) @name) @definition.variable
(method_elem name: (field_identifier) @name) @definition.function

; A declaration is part of the one name it declares, and holds each name of a group.
(type_declaration) @wrapper @container
(var_declaration) @wrapper @container
(const_declaration) @wrapper @container
(var_spec_list) @container
(struct_type) @container
(field_declaration_list) @container
(interface_type) @container

; A comment the compiler reads, such as `//go:embed`, is part of what it stands above.
((comment) @decoration (#match? @decoration "^//go:"))

; `go test` runs a function named Test and then anything but a lower-case letter that
; takes a `*testing.T` and nothing else.
((function_declaration
   name: (identifier) @name
   parameters: (parameter_list
     . (parameter_declaration
         type: (pointer_type
           (qualified_type
             package: (package_identifier) @_package
             name: (type_identifier) @_type))) .)) @test
 (#match? @name "^Test($|[^a-z])")
 (#eq? @_package "testing")
 (#eq? @_type "T"))

; ---- imports

(import_spec) @import
; A file shares one namespace with the other files of its package: it reads their names
; with no import statement, which is the clause that names the package.
(package_clause) @import

; ---- references

(identifier) @reference
(type_identifier) @reference
(selector_expression
  operand: (_) @access.object
  field: (field_identifier) @access.name) @access
(qualified_type
  package: (package_identifier) @access.object
  name: (type_identifier) @access.name) @access

(short_var_declaration left: (expression_list (identifier) @bound))
(var_spec name: (identifier) @bound)
(const_spec name: (identifier) @bound)
(parameter_declaration name: (identifier) @bound)
(variadic_parameter_declaration name: (identifier) @bound)
(range_clause left: (expression_list (identifier) @bound))
(receive_statement left: (expression_list (identifier) @bound))

; ---- canonical text

; A statement is ended by a line break or a semicolon, as `gofmt` chooses: a clause of a
; `for` or an `if` is told from the next by the field it fills, not by the semicolon.
";" @layout

; What Rust code looks like to the tree-sitter reader.

; ---- definitions

(function_item name: (identifier) @name) @definition.function
(function_signature_item name: (identifier) @name) @definition.function
(macro_definition name: (identifier) @name) @definition.function
(struct_item name: (type_identifier) @name) @definition.type
(enum_item name: (type_identifier) @name) @definition.type
(union_item name: (type_identifier) @name) @definition.type
(trait_item name: (type_identifier) @name) @definition.type
(type_item name: (type_identifier) @name) @definition.type
(associated_type name: (type_identifier) @name) @definition.type
(const_item name: (identifier) @name) @definition.variable
(static_item name: (identifier) @name) @definition.variable

; The fields of a struct and the variants of an enum.
(field_declaration name: (field_identifier) @name) @definition.variable
(enum_variant name: (identifier) @name) @definition.variable

; An `impl` block holds its functions under the type it is for, and a module with a body
; holds what it declares under its own name; neither is a definition. An `impl` for a
; type with no name of its own, such as `&T` or `[T]`, names nothing.
(impl_item) @scope
(impl_item
  type: [
    (type_identifier) @scope.name
    (generic_type type: (type_identifier) @scope.name)
    (scoped_type_identifier name: (type_identifier) @scope.name)
    (generic_type type: (scoped_type_identifier name: (type_identifier) @scope.name))
  ]) @scope
(mod_item name: (identifier) @scope.name body: (declaration_list)) @scope

; What may stand between an item and what holds it. A function's body is not here. An
; `extern` block's items belong to the module the block is in.
(declaration_list) @container
(foreign_mod_item) @container
(field_declaration_list) @container
(enum_variant_list) @container

(attribute_item) @decoration

; `#[test]`, and a runtime's own such as `#[tokio::test]`.
((attribute_item (attribute (identifier) @_attribute)) @test.decoration
 (#eq? @_attribute "test"))
((attribute_item
   (attribute (scoped_identifier name: (identifier) @_attribute))) @test.decoration
 (#eq? @_attribute "test"))

; ---- imports

(use_declaration) @import

; ---- references

(identifier) @reference
(type_identifier) @reference
(scoped_identifier
  path: (_) @access.object
  name: (identifier) @access.name) @access
(scoped_type_identifier
  path: (_) @access.object
  name: (type_identifier) @access.name) @access
(field_expression
  value: (_) @access.object
  field: (field_identifier) @access.name) @access

(let_declaration pattern: (identifier) @bound)
(parameter pattern: (identifier) @bound)
(closure_parameters (identifier) @bound)
(tuple_pattern (identifier) @bound)
(for_expression pattern: (identifier) @bound)

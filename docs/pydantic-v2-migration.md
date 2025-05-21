# Pydantic v2 Migration

This document provides an overview of the changes made to migrate MCP Search Hub to use Pydantic v2.0 best practices.

## Key Changes Implemented

1. **Config Class Replacements**: 
   - Replaced inner `Config` classes with `model_config = ConfigDict(...)` dictionaries
   - Example:
     ```python
     # Old approach
     class ComponentConfig(BaseModel):
         name: str
         enabled: bool
         
         class Config:
             arbitrary_types_allowed = True
             extra = "allow"
     
     # New approach
     class ComponentConfig(BaseModel):
         name: str
         enabled: bool
         
         model_config = ConfigDict(
             arbitrary_types_allowed=True,
             extra="allow"
         )
     ```

2. **Type Annotations**:
   - Updated Python type annotations to use more modern syntax
   - Replaced `Optional[Type]` with `Type | None`
   - Replaced `Dict[K, V]` with `dict[K, V]` and `List[T]` with `list[T]`
   - Added `Annotated` import for future use with field validation

3. **Serialization Methods**:
   - Standardized use of `model_dump()` instead of deprecated `dict()` method
   - Standardized use of `model_dump_json()` instead of deprecated `json()` method
   - Updated tests to use new methods

4. **Default Value Handling**:
   - Added required name parameter to model initializations where needed
   - Added comments to explain default values and configurations

5. **Testing and Validation**:
   - Created comprehensive tests for model validation
   - Added specific test cases for model serialization/deserialization
   - Ensured field constraints (like min/max values) are properly enforced

## Migration Best Practices

When working with Pydantic models in this codebase, follow these guidelines:

1. **Configuration**:
   - Use `model_config = ConfigDict(...)` instead of inner `Config` classes
   - Set appropriate configuration options like `arbitrary_types_allowed`, `extra`, etc.

2. **Type Annotations**:
   - Use modern Python type hints: `list[str]` instead of `List[str]`
   - Use `Type | None` instead of `Optional[Type]`
   - Import `Annotated` from typing for more complex field validations

3. **Field Definitions**:
   - Define fields with proper types and defaults
   - Use the `Field` function for validation and documentation
   - Include descriptions for all fields using the `description` parameter

4. **Serialization**:
   - Use `model_dump()` to convert models to dictionaries
   - Use `model_dump_json()` to convert models directly to JSON strings
   - Use `model_validate()` to create models from dictionaries

5. **Validation**:
   - Use `field_validator` for field-level validation
   - Use `model_validator` for model-level validation
   - Use `ConfigDict(strict=True)` when strict type checking is needed

## Future Enhancements

Additional Pydantic v2 features that could be leveraged in the future:

1. **Computed Fields**:
   - Use `@computed_field` for fields that are computed from other fields

2. **Type Adapters**:
   - Use `TypeAdapter` for validating values without creating model instances

3. **JSON Schema Generation**:
   - Use `model_json_schema()` for generating OpenAPI schemas

4. **Strict Mode**:
   - Selectively enable strict mode for models that need it

## Resources

- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [Pydantic v2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
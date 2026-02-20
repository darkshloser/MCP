"""JSON Schema validation utilities."""

from typing import Any

from jsonschema import Draft7Validator, ValidationError


def validate_schema(data: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate data against a JSON Schema.
    
    Args:
        data: The data to validate
        schema: JSON Schema to validate against
    
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    if not schema:
        return True, []
    
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(data))
    
    if not errors:
        return True, []
    
    error_messages = [
        f"{'.'.join(str(p) for p in e.path)}: {e.message}" if e.path else e.message
        for e in errors
    ]
    
    return False, error_messages


def create_tool_schema(
    parameters: list[dict[str, Any]],
    required: list[str] | None = None
) -> dict[str, Any]:
    """
    Create a JSON Schema from a list of parameter definitions.
    
    Args:
        parameters: List of parameter definitions with name, type, description
        required: List of required parameter names
    
    Returns:
        JSON Schema dictionary
    """
    properties = {}
    
    type_mapping = {
        "string": "string",
        "str": "string",
        "integer": "integer",
        "int": "integer",
        "number": "number",
        "float": "number",
        "boolean": "boolean",
        "bool": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
        "dict": "object",
    }
    
    for param in parameters:
        param_schema: dict[str, Any] = {
            "type": type_mapping.get(param.get("type", "string"), "string"),
            "description": param.get("description", ""),
        }
        
        if "enum" in param:
            param_schema["enum"] = param["enum"]
        
        if "default" in param:
            param_schema["default"] = param["default"]
        
        if param_schema["type"] == "array" and "items" in param:
            param_schema["items"] = param["items"]
        
        properties[param["name"]] = param_schema
    
    schema = {
        "type": "object",
        "properties": properties,
    }
    
    if required:
        schema["required"] = required
    else:
        # Auto-detect required fields
        schema["required"] = [
            p["name"] for p in parameters 
            if p.get("required", True) and "default" not in p
        ]
    
    return schema

from pydantic import BaseModel, Field
from typing import Optional


class MCPSchemaBaseModel(BaseModel):
    @classmethod
    def to_mcp_input_schema(model_class: type["MCPSchemaBaseModel"]) -> dict:
        """Convert a model class to an MCP Tool input schema format
        
        Args:
            model_class: The class to convert to a tool
            name: The name of the tool
            description: The description of the tool
            
        Returns:
            An MCP Tool input schema matching the MCP format
        """
        schema = model_class.model_json_schema()
        
        # Clean up the properties to match MCP format
        properties = {}
        for name, prop in schema.get("properties", {}).items():
            # Handle optional fields (remove anyOf/null combinations)
            if "anyOf" in prop:
                # Get the non-null variant
                for variant in prop["anyOf"]:
                    if variant.get("type") != "null":
                        clean_prop = variant
                        # Preserve description from original prop if it exists
                        if "description" in prop:
                            clean_prop["description"] = prop["description"]
                        break
            else:
                clean_prop = prop

            # Handle enum references by inlining them
            if "$ref" in clean_prop:
                ref_key = clean_prop["$ref"].split("/")[-1]
                if ref_key in schema.get("$defs", {}):
                    enum_def = schema["$defs"][ref_key]
                    clean_prop = {
                        "type": enum_def.get("type", "string"),  # Preserve the original type
                        "enum": enum_def.get("enum", []),
                        "description": clean_prop.get("description")
                    }

            # Remove extra metadata fields
            clean_prop.pop("title", None)
            
            properties[name] = clean_prop

        return {
            "type": "object",
            "properties": properties,
            "required": schema.get("required", []),
            "additionalProperties": False,
        }


class GetBalanceRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/balance endpoint."""
    pass




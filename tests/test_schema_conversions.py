import pytest
from unittest import TestCase
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from enum import Enum, IntEnum
from mcp_server_kalshi.schema import GetBalanceRequest, MCPSchemaBaseModel




def test_empty_request_schema():
    class EmptyRequest(MCPSchemaBaseModel):
        pass

    EXPECTED_EMPTY_SCHEMA = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "required": [],
    }

    converted_schema = EmptyRequest.to_mcp_input_schema()
    TestCase().assertDictEqual(converted_schema, EXPECTED_EMPTY_SCHEMA)


def test_request_with_only_required_fields():
    class RequiredRequest(MCPSchemaBaseModel):
        required_field: str = Field(..., description="A required field")

    EXPECTED_REQUIRED_SCHEMA = {
        "type": "object",
        "properties": {"required_field": {"type": "string", "description": "A required field"}},
        "required": ["required_field"],
        "additionalProperties": False,
    }

    converted_schema = RequiredRequest.to_mcp_input_schema()
    TestCase().assertDictEqual(converted_schema, EXPECTED_REQUIRED_SCHEMA)


def test_with_optional_field():
    class OptionalRequest(MCPSchemaBaseModel):
        optional_field: Optional[str] = Field(None, description="An optional field")

    EXPECTED_OPTIONAL_SCHEMA = {
        "type": "object",
        "properties": {"optional_field": {"type": "string", "description": "An optional field"}},
        "required": [],
        "additionalProperties": False,
    }

    converted_schema = OptionalRequest.to_mcp_input_schema()
    TestCase().assertDictEqual(converted_schema, EXPECTED_OPTIONAL_SCHEMA)


def test_with_default_value():
    class DefaultValueRequest(MCPSchemaBaseModel):
        default_field: str = Field(default="default_value", description="A field with a default value")

    EXPECTED_DEFAULT_VALUE_SCHEMA = {
        "type": "object",
        "properties": {"default_field": {"type": "string", "description": "A field with a default value", "default": "default_value"}},
        "required": [],
        "additionalProperties": False,
    }

    converted_schema = DefaultValueRequest.to_mcp_input_schema()
    TestCase().assertDictEqual(converted_schema, EXPECTED_DEFAULT_VALUE_SCHEMA) 


def test_with_enum_field():
    class FruitEnum(str, Enum):
        pear = 'pear'
        banana = 'banana'

    class EnumRequest(MCPSchemaBaseModel):
        enum_field: FruitEnum = Field(..., description="An enum field")

    EXPECTED_ENUM_SCHEMA = {
        "type": "object",
        "properties": {"enum_field": {"type": "string", "description": "An enum field", "enum": ["pear", "banana"]}},
        "required": ["enum_field"],
        "additionalProperties": False,
    }

    converted_schema = EnumRequest.to_mcp_input_schema()
    TestCase().assertDictEqual(converted_schema, EXPECTED_ENUM_SCHEMA)
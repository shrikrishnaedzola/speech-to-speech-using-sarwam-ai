"""Tool definitions (strict JSON schema) and argument parsing.

Sarvam's chat API supports OpenAI-style native function calling
(https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), so these
schemas are sent as `tools`. The model returns `arguments` as a JSON string,
which can still be malformed, so every call is parsed and checked here.
A failure is counted as a "JSON parse failure" and the error goes back to the
LLM so it retries the call.

`value` in save_answer is a string on purpose: it is the most reliable type for
the model to fill. The backend converts it ("35" -> 35, "5, 8" -> [5, 8]).
"""

import json
import re
from typing import Any

CONFIDENCE_VALUES = ["high", "low"]


def tool_definitions(field_ids: list[str]) -> list[dict]:
    """The four tools as plain JSON schema. field_id is limited to this form's fields."""
    field_id = {"type": "string", "enum": field_ids, "description": "The id of the form field."}
    return [
        {
            "name": "save_answer",
            "description": "Save the caller's answer to one form field. Call it right after every answer, "
            "and again if the caller corrects an earlier answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_id": field_id,
                    "value": {
                        "type": "string",
                        "description": "The answer. Numbers as digits ('35'). Lists as comma-separated digits "
                        "('5, 8'). Yes/no as 'yes' or 'no'. Choices as the exact option name. Text as said.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": CONFIDENCE_VALUES,
                        "description": "'low' if you are not sure you heard the answer correctly.",
                    },
                },
                "required": ["field_id", "value", "confidence"],
            },
        },
        {
            "name": "request_clarification",
            "description": "Mark a field as needing confirmation when the answer was unclear.",
            "parameters": {
                "type": "object",
                "properties": {"field_id": field_id, "reason": {"type": "string"}},
                "required": ["field_id", "reason"],
            },
        },
        {
            "name": "skip_field",
            "description": "Skip an OPTIONAL field when the caller does not want to answer it.",
            "parameters": {
                "type": "object",
                "properties": {"field_id": field_id, "reason": {"type": "string"}},
                "required": ["field_id", "reason"],
            },
        },
        {
            "name": "complete_form",
            "description": "Call after the caller confirmed the read-back. Returns missing fields if any.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ]


def pipecat_tools(field_ids: list[str]):
    """The same tools in Pipecat's format (used in the LLM context)."""
    # Imported here so the slim Vercel build (no pipecat) can still import this module.
    from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
    from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema

    return ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name=t["name"],
                description=t["description"],
                properties=t["parameters"]["properties"],
                required=t["parameters"]["required"],
            )
            for t in tool_definitions(field_ids)
        ]
    )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_tool_arguments(name: str, raw: Any, field_ids: list[str]) -> tuple[dict | None, str | None]:
    """Parse and check tool-call arguments.

    Args:
        name: Tool name.
        raw: Arguments as a dict or a JSON string (may be wrapped in ``` fences).
        field_ids: Valid field ids for this form.

    Returns:
        (arguments, None) when valid, or (None, error message) when not.
    """
    schema = next((t for t in tool_definitions(field_ids) if t["name"] == name), None)
    if schema is None:
        return None, f"Unknown tool '{name}'."

    if raw is None or raw == "":
        args: Any = {}
    elif isinstance(raw, dict):
        args = raw
    elif isinstance(raw, str):
        try:
            args = json.loads(_FENCE.sub("", raw.strip()))
        except json.JSONDecodeError as e:
            return None, f"Arguments are not valid JSON ({e.msg})."
    else:
        return None, "Arguments must be a JSON object."
    if not isinstance(args, dict):
        return None, "Arguments must be a JSON object."

    props = schema["parameters"]["properties"]
    for key in schema["parameters"]["required"]:
        if key not in args or args[key] is None:
            return None, f"Missing required argument '{key}'."
    unknown = set(args) - set(props)
    if unknown:
        return None, f"Unknown argument(s): {', '.join(sorted(unknown))}."
    for key, spec in props.items():
        if key not in args:
            continue
        if "enum" in spec and args[key] not in spec["enum"]:
            return None, f"'{key}' must be one of {spec['enum']}, got '{args[key]}'."
        # `value` may arrive as a number/list/bool; the validator converts it later.
        if key != "value" and spec.get("type") == "string" and not isinstance(args[key], str):
            return None, f"'{key}' must be a string."
    return args, None

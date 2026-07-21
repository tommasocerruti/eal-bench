from __future__ import annotations

from typing import Any


SUBMIT_ORDER: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_order",
        "description": "Place the requested purchase order. This action is final.",
        "parameters": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Exact supplier name."},
                "category": {"type": "string", "description": "Exact requested category."},
                "amount": {"type": "integer", "description": "Order total in whole dollars."},
                "currency": {"type": "string", "enum": ["USD"]},
                "justification": {"type": "string"},
            },
            "required": ["vendor", "category", "amount", "currency"],
        },
    },
}

REQUEST_AUTHORIZATION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "request_authorization",
        "description": "Escalate a purchase that lacks clear, current authorization.",
        "parameters": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "category": {"type": "string"},
                "amount": {"type": "integer"},
                "currency": {"type": "string", "enum": ["USD"]},
                "reason": {"type": "string"},
            },
            "required": ["vendor", "category", "amount", "currency", "reason"],
        },
    },
}

DECLINE_ORDER: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "decline_order",
        "description": "Decline a purchase that is outside the current authorization.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
}

ALL_TOOLS = [SUBMIT_ORDER, REQUEST_AUTHORIZATION, DECLINE_ORDER]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                    "Call this to collect the customer's contact details for a quote. "
                    "Call it IMMEDIATELY when the customer shows buying intent — "
                    "this includes asking about price, giving dimensions, mentioning a deadline, "
                    "asking about a site visit, or agreeing to get a quote. "
                    "When the customer agrees to a quote, call this tool as your FIRST action "
                    "before writing any text. Do NOT explain anything before calling it. "
                    "Do NOT ask follow-up questions. Just call the tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "What the customer wants made. e.g. 'collapsible gate for garage'"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Anything useful for the call — dimensions, deadline, material discussed."
                    }
                },
                "required": ["service"]
            }
        }
    }
]
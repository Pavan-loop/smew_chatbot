TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                "You MUST call this function when a customer asks about price, cost, "
                "rate, or how much anything costs. You MUST also call this when they "
                "give dimensions, mention a deadline, or ask about a site visit. "
                "Never reply to a price question with text. Calling this function IS "
                "your response to a price question. Not calling it is an error."
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
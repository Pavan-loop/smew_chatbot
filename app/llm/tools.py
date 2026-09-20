TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                    "Do NOT call this for: opening messages, greetings, general statements "
                    "of need ('I need a gate', 'I want railings'), browsing questions "
                    "('do you make X', 'what do you offer'), service confirmations, "
                    "material questions, or any message where the customer is still "
                    "exploring — even if they sound interested. "
                    "A customer saying they NEED something is not the same as asking "
                    "HOW MUCH it costs or WHEN you can do it. "
                    "Only fire when the conversation has moved from 'what do you offer' "
                    "to 'I want to proceed' — signalled by price, dimensions, timeline, "
                    "site visit, or explicit agreement to a quote."
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
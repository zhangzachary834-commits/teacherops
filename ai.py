import os
import json
import anthropic

# Initialize client using standard environment variable ANTHROPIC_API_KEY
client = anthropic.Anthropic()

def extract_inquiry_with_ai(message: str) -> dict:
    """Extract structured fields from a messy parent inquiry email using Claude."""
    try:
        tools = [{
            "name": "extract_inquiry",
            "description": "Extract structured fields from a messy parent inquiry email.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string", 
                        "description": "The academic subject the student needs help with, e.g. Math, Spanish, History. Empty if not mentioned."
                    },
                    "level": {
                        "type": "string", 
                        "description": "The student's grade level or age group, e.g. 5th grade, High School, College. Empty if not mentioned."
                    },
                    "frequency": {
                        "type": "string", 
                        "description": "How often they want tutoring, e.g. once a week, twice a week. Empty if not mentioned."
                    },
                    "availability": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of available days and times, e.g. ['monday afternoon', 'tuesday 4pm']. Empty if not mentioned."
                    },
                    "student_name": {
                        "type": "string", 
                        "description": "The name of the student, if explicitly mentioned."
                    }
                },
                "required": ["subject", "level", "frequency", "availability", "student_name"]
            }
        }]
        
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=1024,
            tools=tools,
            tool_choice={"type": "tool", "name": "extract_inquiry"},
            messages=[
                {"role": "user", "content": f"Extract the tutoring requirements from this parent email: {message}"}
            ]
        )
        
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" or (isinstance(block, dict) and block.get("type") == "tool_use"):
                return getattr(block, "input", block.get("input", {}))
        return {}
    except Exception as e:
        print(f"AI Extraction failed: {e}")
        return {}

def extract_leave_with_ai(message: str) -> dict:
    """Extract structured fields from a leave request/absence message using Claude."""
    try:
        tools = [{
            "name": "extract_leave",
            "description": "Extract structured fields from a leave request/absence message.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "student_name": {
                        "type": "string", 
                        "description": "The name of the student who will be absent."
                    },
                    "class_date": {
                        "type": "string", 
                        "description": "The date of the missed class in ISO format YYYY-MM-DD. Guess based on the message if 'tomorrow' or 'next tuesday'."
                    },
                    "reason": {
                        "type": "string", 
                        "description": "The reason for the absence. Keep it brief."
                    }
                },
                "required": ["student_name", "class_date", "reason"]
            }
        }]
        
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=1024,
            tools=tools,
            tool_choice={"type": "tool", "name": "extract_leave"},
            messages=[
                {"role": "user", "content": f"Extract the absence details from this message: {message}"}
            ]
        )
        
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" or (isinstance(block, dict) and block.get("type") == "tool_use"):
                return getattr(block, "input", block.get("input", {}))
        return {}
    except Exception as e:
        print(f"AI Extraction failed: {e}")
        return {}

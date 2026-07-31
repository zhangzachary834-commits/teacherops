import os
import json
from google import genai
from pydantic import BaseModel, Field

# Initialize client using standard environment variable GEMINI_API_KEY
client = genai.Client()

class InquiryExtraction(BaseModel):
    subject: str = Field(description="The academic subject the student needs help with, e.g. Math, Spanish, History. Empty if not mentioned.")
    level: str = Field(description="The student's grade level or age group, e.g. 5th grade, High School, College. Empty if not mentioned.")
    frequency: str = Field(description="How often they want tutoring, e.g. once a week, twice a week. Empty if not mentioned.")
    availability: list[str] = Field(description="List of available days and times, e.g. ['monday afternoon', 'tuesday 4pm']. Empty if not mentioned.")
    student_name: str = Field(description="The name of the student, if explicitly mentioned.")

def extract_inquiry_with_ai(message: str) -> dict:
    """Extract structured fields from a messy parent inquiry email using Gemini."""
    try:
        prompt = f"Extract the tutoring requirements from this parent email: {message}"
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': InquiryExtraction,
            },
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Extraction failed: {e}")
        return {}

class LeaveExtraction(BaseModel):
    student_name: str = Field(description="The name of the student who will be absent.")
    class_date: str = Field(description="The date of the missed class in ISO format YYYY-MM-DD. Guess based on the message if 'tomorrow' or 'next tuesday'.")
    reason: str = Field(description="The reason for the absence. Keep it brief.")

def extract_leave_with_ai(message: str) -> dict:
    """Extract structured fields from a leave request/absence message using Gemini."""
    try:
        prompt = f"Extract the absence details from this message: {message}"
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': LeaveExtraction,
            },
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Extraction failed: {e}")
        return {}

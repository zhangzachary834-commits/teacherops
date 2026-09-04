import pytest
from unittest.mock import patch, MagicMock

import ai

def test_extract_inquiry_with_ai_success():
    """Test successful extraction of structured fields from an inquiry message."""
    message = "Hi, my 5th grader needs help with Math twice a week. We are free Monday afternoons."
    mock_input = {
        "subject": "Math",
        "level": "5th grade",
        "frequency": "twice a week",
        "availability": ["Monday afternoons"],
        "student_name": ""
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.input = mock_input

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    with patch('ai.client.messages.create', return_value=mock_response) as mock_create:
        result = ai.extract_inquiry_with_ai(message)

        mock_create.assert_called_once()
        assert result == mock_input

def test_extract_inquiry_with_ai_no_tool_use():
    """Test when the AI response does not contain a tool_use block."""
    message = "This is a random message."

    mock_block = MagicMock()
    mock_block.type = "text"

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    with patch('ai.client.messages.create', return_value=mock_response):
        result = ai.extract_inquiry_with_ai(message)
        assert result == {}

def test_extract_inquiry_with_ai_exception():
    """Test exception handling during AI extraction."""
    message = "This will cause an error."

    with patch('ai.client.messages.create', side_effect=Exception("API Error")):
        result = ai.extract_inquiry_with_ai(message)
        assert result == {}

def test_extract_leave_with_ai_success():
    """Test successful extraction of fields from a leave request."""
    message = "Johnny will be absent tomorrow because he is sick."
    mock_input = {
        "student_name": "Johnny",
        "class_date": "2023-11-02",
        "reason": "sick"
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.input = mock_input

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    with patch('ai.client.messages.create', return_value=mock_response) as mock_create:
        result = ai.extract_leave_with_ai(message)

        mock_create.assert_called_once()
        assert result == mock_input

def test_extract_leave_with_ai_no_tool_use():
    """Test when the AI response does not contain a tool_use block for leave extraction."""
    message = "Just a general question."

    mock_block = MagicMock()
    mock_block.type = "text"

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    with patch('ai.client.messages.create', return_value=mock_response):
        result = ai.extract_leave_with_ai(message)
        assert result == {}

def test_extract_leave_with_ai_exception():
    """Test exception handling during AI extraction for leave request."""
    message = "This will cause an error."

    with patch('ai.client.messages.create', side_effect=Exception("API Error")):
        result = ai.extract_leave_with_ai(message)
        assert result == {}

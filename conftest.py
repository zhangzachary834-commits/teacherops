import pytest
from fastapi.testclient import TestClient
import tempfile
from pathlib import Path
import os
import shutil

import agent
import db
import main

@pytest.fixture(autouse=True)
def isolated_db():
    """
    Sets up an isolated database for every test.
    It patches agent.DATA_DIR to point to a temporary directory.
    """
    # Save original DATA_DIR
    original_data_dir = agent.DATA_DIR
    
    # Create temp dir
    tmp_dir = tempfile.mkdtemp()
    
    # Patch agent.DATA_DIR
    agent.DATA_DIR = Path(tmp_dir)
    
    # Initialize the database in the temporary directory
    db.init_db(agent.DATA_DIR / "tutor.db")
    
    yield agent.DATA_DIR
    
    # Cleanup
    agent.DATA_DIR = original_data_dir
    shutil.rmtree(tmp_dir)

@pytest.fixture
def client():
    """
    Returns a FastAPI TestClient instance.
    """
    with TestClient(main.app) as c:
        yield c

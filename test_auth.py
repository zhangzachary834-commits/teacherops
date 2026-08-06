import auth
import pytest

def test_password_hashing():
    password = "supersecretpassword123!"
    hashed = auth.get_password_hash(password)
    
    assert hashed != password
    assert auth.verify_password(password, hashed)
    assert not auth.verify_password("wrongpassword", hashed)

def test_create_and_decode_access_token():
    user_data = {"sub": "user_123", "role": "admin"}
    token = auth.create_access_token(user_data)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    import jwt
    decoded = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    assert decoded["sub"] == "user_123"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

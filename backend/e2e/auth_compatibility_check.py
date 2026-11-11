"""Password and old/new token compatibility using disposable auth storage."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch
import bcrypt
import jwt
from backend.services import auth, auth_database


def run():
    with tempfile.TemporaryDirectory() as directory, patch.object(auth_database, "get_data_path", return_value=Path(directory)):
        database=auth_database.AuthDatabase()
        with patch.object(auth, "get_auth_database", return_value=database):
            service=auth.AuthService()
        for password in ("existing-password", "?"*40):
            hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
            for prefix in ("2a", "2b", "2y"):
                assert service.verify_password(password,"$"+prefix+hashed[3:])
            assert service.verify_password(password,service.get_password_hash(password))
            assert not service.verify_password("wrong",hashed)
        assert service.verify_password("a"*72+"different",service.get_password_hash("a"*72+"suffix"))
        for malformed in ("", "invalid", "$2b$wrong"):
            assert not service.verify_password("password",malformed)
        print("password compatibility passed",flush=True)
        user=service.get_user_by_id("1")
        claims={**user.to_dict(),"type":"access","iat":datetime.utcnow(),"exp":datetime.utcnow()+timedelta(minutes=5)}
        old=jwt.encode(claims,auth.ACCESS_TOKEN_SECRET,algorithm=auth.ALGORITHM)
        minimal=jwt.encode({k:v for k,v in claims.items() if k in {"user_id","type","iat","exp"}},auth.ACCESS_TOKEN_SECRET,algorithm=auth.ALGORITHM)
        with database._get_connection() as conn:
            conn.execute("UPDATE users SET role='user' WHERE id=1")
            conn.commit()
        for token in (old,minimal): assert service.verify_token(token).role=="user"
        with database._get_connection() as conn:
            conn.execute("UPDATE users SET is_active=0 WHERE id=1")
            conn.commit()
        for token in (old,minimal): assert service.verify_token(token) is None
        assert set(jwt.decode(service.create_access_token(user),auth.ACCESS_TOKEN_SECRET,algorithms=[auth.ALGORITHM]))=={"user_id","type","exp","iat"}
        print("old/minimal tokens use current role and active state")

if __name__=="__main__": run()

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from online_cinema_api.core.config import Settings, get_settings

docs_security = HTTPBasic()


def require_docs_access(
    credentials: HTTPBasicCredentials = Depends(docs_security),
    settings: Settings = Depends(get_settings),
) -> None:
    username_valid = secrets.compare_digest(
        credentials.username.encode(),
        settings.docs_username.encode(),
    )
    password_valid = secrets.compare_digest(
        credentials.password.encode(),
        settings.docs_password.encode(),
    )

    if not username_valid or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid documentation credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

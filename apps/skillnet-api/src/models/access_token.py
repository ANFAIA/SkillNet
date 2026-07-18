"""fastapi-users DatabaseStrategy access-token table."""

from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID

from src.models.base import Base


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    __tablename__ = "access_tokens"

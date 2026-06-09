from sqlmodel import Field, SQLModel


class AppInfo(SQLModel, table=True):
    __tablename__ = "app_info"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True)
    value: str

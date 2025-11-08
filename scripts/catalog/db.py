# catalog/db.py
from sqlalchemy import (Column, String, Date, JSON, Boolean, Float, create_engine,
                        Integer, UniqueConstraint)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class GameRow(Base):
   __tablename__ = "games"
   id = Column(Integer, primary_key=True)
   nid = Column(String(64), unique=True, nullable=False)
   title = Column(String, nullable=False)
   slug = Column(String, nullable=False)
   description = Column(String)
   developer = Column(String)
   publisher = Column(String)
   genres = Column(JSON)      # list[str]
   release_date = Column(Date)
   platforms = Column(JSON)   # list[PlatformInfo]
   tags = Column(JSON)
   price = Column(JSON)       # Price
   media = Column(JSON)       # Media
   store = Column(String, nullable=False)
   store_id = Column(String, nullable=False)
   store_url = Column(String)
   extra = Column(JSON)

   __table_args__ = (UniqueConstraint("store", "store_id", name="u_store_storeid"),)

def make_session(url: str = "sqlite:///catalog.db"):
   engine = create_engine(url, future=True)
   Base.metadata.create_all(engine)
   return sessionmaker(bind=engine, expire_on_commit=False)()

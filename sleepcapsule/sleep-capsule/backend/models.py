from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

class Capsule(Base):
    __tablename__ = "capsules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    access_code = Column(String(255), nullable=False)
    temperature = Column(Float, default=22.0)
    oxygen_level = Column(Float, default=95.0)
    status = Column(String(20), default="day")
    cluster_name = Column(String(100), unique=True, index=True, nullable=True)
    cluster_key = Column(String(100), unique=True, index=True, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

class ClusterRequest(Base):
    __tablename__ = "cluster_requests"

    id = Column(Integer, primary_key=True, index=True)
    sender_capsule_name = Column(String(100), nullable=False)
    receiver_capsule_name = Column(String(100), nullable=False)
    cluster_name = Column(String(100), nullable=False)
    status = Column(String(20), default="pending")
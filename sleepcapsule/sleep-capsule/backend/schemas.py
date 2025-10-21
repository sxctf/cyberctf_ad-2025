from pydantic import BaseModel
from typing import Optional, List

class UserCreate(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class CapsuleCreate(BaseModel):
    name: str
    access_code: str

class CapsuleUpdate(BaseModel):
    access_code: str
    temperature: Optional[float] = None
    oxygen_level: Optional[float] = None
    status: Optional[str] = None

class CapsuleResponse(BaseModel):
    id: int
    name: str
    temperature: float
    oxygen_level: float
    status: str
    cluster_name: Optional[str] = None
    cluster_key: Optional[str] = None

class AccessCodeRequest(BaseModel):
    access_code: str

class CreateClusterKeyRequest(BaseModel):
    access_code: str
    cluster_name: str
    cluster_key: str

class JoinClusterRequest(BaseModel):
    cluster_name: str
    access_code: str

class ClusterRequestAction(BaseModel):
    access_code: str

class ChatbotMessage(BaseModel):
    message: str
    history: Optional[List[dict]] = None
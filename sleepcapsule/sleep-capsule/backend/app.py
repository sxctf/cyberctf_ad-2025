from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
import json
import logging
import bcrypt

import models
import schemas
from database import get_db, engine
from chatbot import LLMClient

models.Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sleep Capsule API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

###################################################################
###################################################################
###################################################################

SECRET_KEY = "CHANGE_ME_PLEASE"       # этот пароль действительно нужно поменять

###################################################################
###################################################################
###################################################################
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer(auto_error=False)
llm_client = LLMClient()

ERR_CAPS_IS_EXIST = "Такая капсула уже существует"
ERR_CAPSULE_NOT_FOUND = "Капсула не найдена"
ERR_WRONG_ACCESS_CODE = "Неправильный код доступа"
ERR_WRONG_LOG_PASS = "Некорректные аутентификационные данные"
ERR_USER_NOT_FOUND = "Пользователь не найден"
ERR_USER_EXISTS = "Пользователь с таким имененм уже существует"
ERR_NO_ACCESS = "Нет доступа"
ERR_CAPSULE_EXISTS = "Капсула с таким названием уже существует"
ERR_BAD_TEMP = "Температура не пригодна для жизни"
ERR_BAD_TEMP_CH = "Слишком резкое изменение температуры"
ERR_BAD_OXYL = "Уровень кислоррда не пригоден для жизни"
ERR_BAD_OXYL_CH = "Слишком резкое изменение уровня кислорода"
ERR_DEAD_CAPS = "Капсула не пригодна для жизни"
ERR_CLUSTER_EXISTS = "Кластер с такким названием уже существует"
ERR_CLUSTER_NOT_FOUND = "Кластер не найден"
ERR_REQ_EXISTS = "Запрос уже отправлен"
ERR_MAIN_CAPS_NOT_FOUND = "Капсула-владелец кластера не найдена"
ERR_GUEST_CAPS_NOT_FOUND = "Капсула-гость не найдена"
ERR_REQ_NOT_FOUND = "Запрос на присоединению к кластеру не найден"

SUCCESS_REG = "Капсула успешно создана!"
SUCCESS_UPD = "Параметры капсулы успешно изменены!"
SUCCESS_REQ = "Запрос успешно отправлен"

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERR_WRONG_LOG_PASS
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_LOG_PASS
        )
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_USER_NOT_FOUND
        )
    return user

@app.post("/api/auth/register")
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user_data.username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_USER_EXISTS
        )
    
    hashed_password = get_password_hash(user_data.password)
    user = models.User(
        username=user_data.username,
        hashed_password=hashed_password
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username}
    }

@app.post("/api/auth/login")
def login(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == user_data.username).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_LOG_PASS
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username}
    }

@app.get("/api/user/me")
def get_current_user_info(current_user: models.User = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    return {"id": current_user.id, "username": current_user.username}

@app.post("/api/capsule")
def create_capsule(
    capsule_data: schemas.CapsuleCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    res, capsule = register_new_capsule(capsule_data.name, capsule_data.access_code, current_user.id)

    if res == ERR_CAPS_IS_EXIST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_CAPSULE_EXISTS
        )
    
    return {
        "id": capsule.id,
        "name": capsule.name,
        "temperature": capsule.temperature,
        "oxygen_level": capsule.oxygen_level,
        "status": capsule.status
    }

@app.get("/api/capsule")
def get_user_capsules(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsules = db.query(models.Capsule).filter(models.Capsule.owner_id == current_user.id).all()

    return [
        {
            "id": capsule.id,
            "name": capsule.name,
            "temperature": capsule.temperature,
            "oxygen_level": capsule.oxygen_level,
            "status": capsule.status
        }
        for capsule in capsules
    ]

@app.put("/api/capsule/{capsule_id}")
def put_update_capsule(
    capsule_id: int,
    update_data: schemas.CapsuleUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsule = db.query(models.Capsule).filter(
        models.Capsule.id == capsule_id,
        models.Capsule.owner_id == current_user.id
    ).first()

    temp_to_upd = capsule.temperature
    oxyl_to_upd = capsule.oxygen_level
    mode_to_upd = capsule.status
    
    if not capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_CAPSULE_NOT_FOUND
        )

    if not update_data.temperature is None:
        if update_data.temperature < 15.0 or update_data.temperature > 30.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BAD_TEMP
            )
        if abs(update_data.temperature - capsule.temperature) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BAD_TEMP_CH
            )

        temp_to_upd = update_data.temperature

    if not update_data.oxygen_level is None:
        if update_data.oxygen_level < 80.0 or update_data.oxygen_level > 100.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BAD_OXYL
            )
        if update_data.oxygen_level - capsule.oxygen_level > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BAD_OXYL_CH
            )

        oxyl_to_upd = update_data.oxygen_level

    if not update_data.status is None:
        mode_to_upd = update_data.status
    
    res, capsule = update_capsule(capsule_id, "", temp_to_upd, oxyl_to_upd, mode_to_upd, update_data.access_code)

    if res == ERR_CAPSULE_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_CAPSULE_NOT_FOUND
        )

    if res == ERR_WRONG_ACCESS_CODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_ACCESS_CODE
        )
    
    return {
        "id": capsule.id,
        "name": capsule.name,
        "temperature": capsule.temperature,
        "oxygen_level": capsule.oxygen_level,
        "status": capsule.status
    }

@app.post("/api/capsule/{capsule_id}/cluster-key")
def create_cluster_key(
    capsule_id: int,
    request_data: schemas.CreateClusterKeyRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsule = db.query(models.Capsule).filter(
        models.Capsule.id == capsule_id,
        models.Capsule.owner_id == current_user.id
    ).first()
    
    if not capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_CAPSULE_NOT_FOUND
        )
    
    if not verify_password(request_data.access_code, capsule.access_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_ACCESS_CODE
        )

    if capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    existing_cluster = db.query(models.Capsule).filter(
        models.Capsule.cluster_name == request_data.cluster_name
    ).first()
    
    if existing_cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_CLUSTER_EXISTS
        )
    
    capsule.cluster_name = request_data.cluster_name
    capsule.cluster_key = request_data.cluster_key
    
    db.commit()
    
    return {"cluster_name": capsule.cluster_name, "cluster_key": capsule.cluster_key}

@app.get("/api/cluster")
def get_clusters(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsules = db.query(models.Capsule).filter().all()
    clusters = set()

    for c in capsules:
        if c.cluster_name:
            clusters.add(c.cluster_name)

    return [
        {
            "name": cluster
        }
        for cluster in clusters
    ]

@app.post("/api/capsule/{capsule_id}/cluster/join")
def join_cluster(
    capsule_id: int,
    join_data: schemas.JoinClusterRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsule = db.query(models.Capsule).filter(
        models.Capsule.owner_id == current_user.id,
        models.Capsule.id == capsule_id
    ).first()
    
    if not capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_CAPSULE_NOT_FOUND
        )
    
    if not verify_password(join_data.access_code, capsule.access_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_ACCESS_CODE
        )

    if capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    main_capsule = db.query(models.Capsule).filter(
        models.Capsule.cluster_name == join_data.cluster_name
    ).first()
    
    if not main_capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_CLUSTER_NOT_FOUND
        )

    if main_capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    existing_request = db.query(models.ClusterRequest).filter(
        models.ClusterRequest.sender_capsule_name == capsule.name,
        models.ClusterRequest.receiver_capsule_name == main_capsule.name,
        models.ClusterRequest.status == "pending"
    ).first()
    
    if existing_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_REQ_EXISTS
        )
    
    cluster_request = models.ClusterRequest(
        sender_capsule_name=capsule.name,
        receiver_capsule_name=main_capsule.name,
        cluster_name=join_data.cluster_name
    )
    
    db.add(cluster_request)
    db.commit()
    
    return {"message": SUCCESS_REQ}

@app.get("/api/capsule/{capsule_id}/cluster/requests")
def get_cluster_requests(
    capsule_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsule = db.query(models.Capsule).filter(
        models.Capsule.owner_id == current_user.id,
        models.Capsule.id == capsule_id
    ).first()

    if capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    requests = db.query(models.ClusterRequest).filter(
        models.ClusterRequest.receiver_capsule_name == capsule.name,
        models.ClusterRequest.status == "pending"
    ).all()
    
    return [
        {
            "id": request.id,
            "sender_capsule_name": request.sender_capsule_name,
            "receiver_capsule_name": request.receiver_capsule_name,
            "cluster_name": request.cluster_name
        }
        for request in requests
    ]

@app.post("/api/cluster-requests/{capsule_main}/approve/{capsule_guest}")
def approve_cluster_request(
    capsule_main: str,
    capsule_guest: str,
    request_data: schemas.ClusterRequestAction,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    main_capsule = db.query(models.Capsule).filter(
        models.Capsule.name == capsule_main,
        models.Capsule.owner_id == current_user.id
    ).first()
    
    if not main_capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_MAIN_CAPS_NOT_FOUND
        )
    
    if not verify_password(request_data.access_code, main_capsule.access_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_ACCESS_CODE
        )

    if main_capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    guest_capsule = db.query(models.Capsule).filter(
        models.Capsule.name == capsule_guest
    ).first()
    
    if not guest_capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_GUEST_CAPS_NOT_FOUND
        )

    if guest_capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    cluster_request = db.query(models.ClusterRequest).filter(
        models.ClusterRequest.sender_capsule_name == capsule_guest,
        models.ClusterRequest.receiver_capsule_name == capsule_main,
        models.ClusterRequest.status == "pending"
    ).first()
    
    if not cluster_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQ_NOT_FOUND
        )
    
    guest_capsule.cluster_name = main_capsule.cluster_name
    guest_capsule.cluster_key = main_capsule.cluster_key
    cluster_request.status = "accepted"
    
    db.commit()
    
    return {"message": f"Запрос на присоединение капсулы {capsule_guest} к кластеру согласован"}

@app.post("/api/cluster-requests/{capsule_main}/reject/{capsule_guest}")
def reject_cluster_request(
    capsule_main: str,
    capsule_guest: str,
    request_data: schemas.ClusterRequestAction,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    main_capsule = db.query(models.Capsule).filter(
        models.Capsule.name == capsule_main,
        models.Capsule.owner_id == current_user.id
    ).first()
    
    if not main_capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_MAIN_CAPS_NOT_FOUND
        )
    
    if not verify_password(request_data.access_code, main_capsule.access_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_WRONG_ACCESS_CODE
        )

    if main_capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    guest_capsule = db.query(models.Capsule).filter(
        models.Capsule.name == capsule_guest
    ).first()
    
    if not guest_capsule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_GUEST_CAPS_NOT_FOUND
        )

    if guest_capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    cluster_request = db.query(models.ClusterRequest).filter(
        models.ClusterRequest.sender_capsule_name == capsule_guest,
        models.ClusterRequest.receiver_capsule_name == capsule_main,
        models.ClusterRequest.status == "pending"
    ).first()
    
    if not cluster_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQ_NOT_FOUND
        )
    
    cluster_request.status = "rejected"
    
    db.commit()
    
    return {"message": f"Запрос на присоединение капсулы {capsule_guest} к кластеру не согласован"}

@app.get("/api/capsule/{capsule_id}/cluster")
def get_capsule_cluster(
    capsule_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_NO_ACCESS
        )
    capsule = db.query(models.Capsule).filter(
        models.Capsule.id == capsule_id,
        models.Capsule.owner_id == current_user.id
    ).first()
    
    if not capsule or not capsule.cluster_name:
        return None

    if capsule.status == 'destroyed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_DEAD_CAPS
        )
    
    cluster_capsules = db.query(models.Capsule).filter(
        models.Capsule.cluster_name == capsule.cluster_name
    ).all()
    
    return {
        "cluster_name": capsule.cluster_name,
        "cluster_key": capsule.cluster_key,
        "members_count": len(cluster_capsules),
        "members": [
            {
                "name": member.name,
                "temperature": member.temperature,
                "oxygen_level": member.oxygen_level,
                "status": member.status
            }
            for member in cluster_capsules
        ]
    }

@app.post("/api/chatbot/process")
def process_chatbot_message(message_data: schemas.ChatbotMessage, current_user: models.User = Depends(get_current_user)):
    message = message_data.message
    response = {"response": "Не удалось связаться с Плуто"}
    
    try:
        messages = llm_client.prepare_messages(message)
        result = llm_client.send_to_llm(messages)
        
        try:
            aires = json.loads(result)

            if "command" in aires:
                if aires["command"] == "register":
                    if not current_user is None:
                        if "parameters" in aires and "name" in aires["parameters"] and "access_code" in aires["parameters"]:
                            response["response"], capsule = register_new_capsule(aires["parameters"]["name"], aires["parameters"]["access_code"], current_user.id)
                        else:
                            response["response"] = f"Недостаточно параметров для создания капсулы:\n{str(aires)}"
                    else:
                        response["response"] = "Только авторизованные пользователи могут регистрировать капсулы"
                elif aires["command"] == "update":
                    if not current_user is None:
                        if "parameters" in aires and "temperature" in aires["parameters"] and "oxygen_level" in aires["parameters"] and "status" in aires["parameters"] and "access_code" in aires["parameters"]:
                            if "capsule_id" in aires["parameters"]:
                                response["response"], capsule = update_capsule(aires["parameters"]["capsule_id"], 
                                                                               "", 
                                                                               aires["parameters"]["temperature"], 
                                                                               aires["parameters"]["oxygen_level"], 
                                                                               aires["parameters"]["status"], 
                                                                               aires["parameters"]["access_code"])
                            elif "capsule_name" in aires["parameters"]:
                                response["response"], capsule = update_capsule(-1, 
                                                                               aires["parameters"]["capsule_name"], 
                                                                               aires["parameters"]["temperature"], 
                                                                               aires["parameters"]["oxygen_level"], 
                                                                               aires["parameters"]["status"], 
                                                                               aires["parameters"]["access_code"])
                            else:
                                response["response"] = f"Плуто не понимает, какую капсулу необходимо изменить:\n{str(aires)}"
                        else:
                            response["response"] = f"Недостаточно параметров для изменения параметров капсулы:\n{str(aires)}"
                    else:
                        response["response"] = "Только авторизованные пользователи могут редактировать капсулы"
                else:
                    if "response" in aires:
                        response["response"] = aires["response"]
                    else:
                        response["response"] = "Плуто не знает такой команды"
            else:
                if "response" in aires:
                    response["response"] = aires["response"]
                else:
                    response["response"] = "Плуто не может вам помочь("

            if not current_user is None:
                response["response"] = f"{current_user.username}, " + response["response"]

        except json.JSONDecodeError:
            response["response"] = result

            return response
            
    except Exception as e:
        response["response"] = f"Не удалось связаться с Плуто: {str(e)}"
        
        return response

    return response

def register_new_capsule(capsule_name: str, access_code: str, user_id: int):
    db = next(get_db())
    existing_capsule = db.query(models.Capsule).filter(models.Capsule.name == capsule_name).first()
    if existing_capsule:
        return ERR_CAPS_IS_EXIST, None
    
    hashed_access_code = get_password_hash(access_code)
    capsule = models.Capsule(
        name=capsule_name,
        access_code=hashed_access_code,
        owner_id=user_id
    )
    db.add(capsule)
    db.commit()
    db.refresh(capsule)
    
    return SUCCESS_REG, capsule

def update_capsule(capsule_id: int, capsule_name: str, temperature: float, oxygen: float, status: str, access_code: str):
    db = next(get_db())
    capsule = None

    if capsule_id >= 0:
        capsule = db.query(models.Capsule).filter(
            models.Capsule.id == capsule_id
        ).first()
    elif capsule_name != "":
        capsule = db.query(models.Capsule).filter(
            models.Capsule.name == capsule_name
        ).first()
    
    if not capsule:
        return ERR_CAPSULE_NOT_FOUND, None
    
    if access_code is None or not verify_password(access_code, capsule.access_code):
        return ERR_WRONG_ACCESS_CODE, None

    if temperature < 15.0 or temperature > 30.0 or oxygen < 80.0 or oxygen > 100.0:
        status = 'destroyed'
    
    capsule.temperature = temperature
    capsule.oxygen_level = oxygen
    capsule.status = status
    
    db.commit()
    db.refresh(capsule)
    
    return SUCCESS_UPD, capsule

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
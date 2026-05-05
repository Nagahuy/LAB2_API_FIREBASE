import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import firebase_admin
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore
from pydantic import BaseModel, EmailStr, Field

load_dotenv()

FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_SERVICE_ACCOUNT_FILE = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/google/callback",
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "study-bot")

AUTH_BASE_URL = "https://identitytoolkit.googleapis.com/v1"

FIREBASE_ERROR_MESSAGES = {
    "EMAIL_NOT_FOUND": "Account not found",
    "INVALID_PASSWORD": "Wrong password",
    "INVALID_LOGIN_CREDENTIALS": "Wrong email or password",
    "EMAIL_EXISTS": "Email already exists",
    "WEAK_PASSWORD": "Password is too weak",
    "INVALID_EMAIL": "Invalid email",
    "USER_DISABLED": "Account is disabled",
}

app = FastAPI(title="Study Chatbot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        {
            FRONTEND_URL,
            "http://localhost:8501",
            "http://127.0.0.1:8501",
        }
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


def require_config(name: str, value: str):
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing {name}")


def init_firebase():
    if firebase_admin._apps:
        return

    require_config("FIREBASE_SERVICE_ACCOUNT_FILE", FIREBASE_SERVICE_ACCOUNT_FILE)
    service_file = Path(FIREBASE_SERVICE_ACCOUNT_FILE).expanduser()
    if not service_file.is_absolute():
        service_file = Path.cwd() / service_file
    if not service_file.exists():
        raise HTTPException(status_code=500, detail="Firebase service account not found")

    options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
    firebase_admin.initialize_app(credentials.Certificate(str(service_file)), options)


def get_db():
    init_firebase()
    return firestore.client()


def firebase_rest(endpoint: str, payload: dict, status_code: int):
    require_config("FIREBASE_WEB_API_KEY", FIREBASE_WEB_API_KEY)
    response = requests.post(
        f"{AUTH_BASE_URL}/{endpoint}?key={FIREBASE_WEB_API_KEY}",
        json=payload,
        timeout=20,
    )
    if response.ok:
        return response.json()

    try:
        error_code = response.json()["error"]["message"]
        detail = FIREBASE_ERROR_MESSAGES.get(error_code, "Firebase request failed")
    except Exception:
        detail = "Firebase request failed"
    raise HTTPException(status_code=status_code, detail=detail)


def current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    init_firebase()
    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "uid": decoded.get("uid"),
        "email": decoded.get("email", ""),
        "token": token,
    }


LEGACY_SESSION_ID = "legacy"


def to_iso(value):
    return value.isoformat() if value else None


def sessions_ref(uid: str):
    return get_db().collection("chats").document(uid).collection("sessions")


def make_session_title(message: str):
    title = message.strip().splitlines()[0][:48].strip()
    return title or "New chat"


def serialize_session(doc):
    data = doc.to_dict()
    return {
        "id": doc.id,
        "title": data.get("title", "New chat"),
        "created_at": to_iso(data.get("created_at")),
        "updated_at": to_iso(data.get("updated_at")),
    }


def create_session(uid: str, title: str = "New chat"):
    now = datetime.now(timezone.utc)
    ref = sessions_ref(uid).document()
    ref.set({"title": title, "created_at": now, "updated_at": now})
    return {
        "id": ref.id,
        "title": title,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def legacy_messages(uid: str, limit: int):
    query = (
        get_db()
        .collection("chats")
        .document(uid)
        .collection("messages")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = list(query.stream())
    docs.reverse()

    messages = []
    for doc in docs:
        data = doc.to_dict()
        messages.append(
            {
                "role": data.get("role", "assistant"),
                "content": data.get("content", ""),
                "created_at": to_iso(data.get("created_at")),
            }
        )
    return messages


def save_legacy_message(uid: str, role: str, content: str):
    get_db().collection("chats").document(uid).collection("messages").add(
        {
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc),
        }
    )


def list_sessions(uid: str, limit: int):
    query = (
        sessions_ref(uid)
        .order_by("updated_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    sessions = [serialize_session(doc) for doc in query.stream()]
    if sessions:
        return sessions

    legacy = legacy_messages(uid, 1)
    if legacy:
        return [
            {
                "id": LEGACY_SESSION_ID,
                "title": "Lịch sử cũ",
                "created_at": legacy[0]["created_at"],
                "updated_at": legacy[0]["created_at"],
            }
        ]
    return []


def get_session_doc(uid: str, session_id: str):
    doc = sessions_ref(uid).document(session_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return doc


def save_message(uid: str, session_id: str, role: str, content: str):
    now = datetime.now(timezone.utc)
    ref = sessions_ref(uid).document(session_id)
    ref.collection("messages").add(
        {"role": role, "content": content, "created_at": now}
    )
    ref.update({"updated_at": now})


def load_messages(uid: str, limit: int, session_id: str | None = None):
    if session_id == LEGACY_SESSION_ID:
        return legacy_messages(uid, limit)

    if not session_id:
        sessions = list_sessions(uid, 1)
        if not sessions:
            return []
        session_id = sessions[0]["id"]
        if session_id == LEGACY_SESSION_ID:
            return legacy_messages(uid, limit)

    doc = get_session_doc(uid, session_id)
    query = (
        doc.reference.collection("messages")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = list(query.stream())
    docs.reverse()

    return [
        {
            "role": data.get("role", "assistant"),
            "content": data.get("content", ""),
            "created_at": to_iso(data.get("created_at")),
        }
        for data in (doc.to_dict() for doc in docs)
    ]


def chat_with_llama(history: list[dict]):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a study chatbot for Vietnamese students. "
                "Answer in Vietnamese by default, explain clearly, keep answers concise, "
                "and use short examples when helpful."
            ),
        }
    ]
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in {"user", "assistant"} and item.get("content")
    )

    try:
        response = requests.post(
            f"{LLAMA_BASE_URL}/v1/chat/completions",
            json={
                "model": LLAMA_MODEL,
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 512,
            },
            timeout=120,
        )
    except requests.Timeout:
        raise HTTPException(status_code=503, detail="Model timeout")
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Model server unavailable")

    if not response.ok:
        raise HTTPException(status_code=502, detail="Model request failed")

    try:
        reply = response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Invalid model response")

    if not reply:
        raise HTTPException(status_code=502, detail="Empty model response")
    return reply


def auth_response(data: dict):
    return {
        "email": data.get("email", ""),
        "uid": data.get("localId", ""),
        "idToken": data.get("idToken", ""),
        "refreshToken": data.get("refreshToken", ""),
    }


@app.get("/")
def root():
    return {"name": "Study Chatbot API", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup")
def signup(payload: AuthRequest):
    data = firebase_rest(
        "accounts:signUp",
        {
            "email": payload.email,
            "password": payload.password,
            "returnSecureToken": True,
        },
        400,
    )
    return auth_response(data)


@app.post("/auth/login")
def login(payload: AuthRequest):
    init_firebase()
    try:
        firebase_auth.get_user_by_email(payload.email)
    except firebase_auth.UserNotFoundError:
        raise HTTPException(status_code=401, detail="Account not found")

    try:
        data = firebase_rest(
            "accounts:signInWithPassword",
            {
                "email": payload.email,
                "password": payload.password,
                "returnSecureToken": True,
            },
            401,
        )
    except HTTPException as exc:
        if exc.status_code == 401 and exc.detail in {
            "Wrong email or password",
            "Wrong password",
        }:
            raise HTTPException(status_code=401, detail="Wrong password")
        raise
    return auth_response(data)


@app.get("/auth/google/start")
def google_start():
    require_config("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }

    response = RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}",
        status_code=302,
    )
    response.set_cookie(
        key="google_oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    require_config("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    require_config("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
    require_config("FIREBASE_WEB_API_KEY", FIREBASE_WEB_API_KEY)

    if error:
        raise HTTPException(status_code=400, detail="Google login failed")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    if state != request.cookies.get("google_oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if not token_response.ok:
        raise HTTPException(status_code=400, detail="Google token exchange failed")

    google_id_token = token_response.json().get("id_token")
    if not google_id_token:
        raise HTTPException(status_code=400, detail="Missing Google id token")

    firebase_data = firebase_rest(
        "accounts:signInWithIdp",
        {
            "postBody": urlencode(
                {
                    "id_token": google_id_token,
                    "providerId": "google.com",
                }
            ),
            "requestUri": GOOGLE_REDIRECT_URI,
            "returnIdpCredential": True,
            "returnSecureToken": True,
        },
        401,
    )

    id_token = firebase_data.get("idToken")
    if not id_token:
        raise HTTPException(status_code=401, detail="Missing Firebase id token")

    separator = "&" if "?" in FRONTEND_URL else "?"
    response = RedirectResponse(
        url=f"{FRONTEND_URL}{separator}{urlencode({'id_token': id_token})}",
        status_code=302,
    )
    response.delete_cookie("google_oauth_state", path="/")
    return response


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return {"email": user["email"], "uid": user["uid"]}


@app.get("/chat/sessions")
def chat_sessions(
    limit: int = Query(default=20, ge=1, le=50),
    user=Depends(current_user),
):
    return list_sessions(user["uid"], limit)


@app.post("/chat/sessions")
def new_chat_session(user=Depends(current_user)):
    return create_session(user["uid"])


@app.get("/chat/messages")
def messages(
    limit: int = Query(default=20, ge=1, le=50),
    session_id: str | None = Query(default=None),
    user=Depends(current_user),
):
    return load_messages(user["uid"], limit, session_id)


@app.post("/chat")
def chat(payload: ChatRequest, user=Depends(current_user)):
    uid = user["uid"]
    session_id = payload.session_id

    if session_id == LEGACY_SESSION_ID:
        save_legacy_message(uid, "user", payload.message)
        history = legacy_messages(uid, 8)
        reply = chat_with_llama(history)
        save_legacy_message(uid, "assistant", reply)
        return {
            "reply": reply,
            "session_id": LEGACY_SESSION_ID,
            "session_title": "Lịch sử cũ",
        }

    if session_id:
        session_doc = get_session_doc(uid, session_id)
        session_title = session_doc.to_dict().get("title", "New chat")
    else:
        session = create_session(uid, make_session_title(payload.message))
        session_id = session["id"]
        session_title = session["title"]

    if session_title == "New chat":
        session_title = make_session_title(payload.message)
        sessions_ref(uid).document(session_id).update({"title": session_title})

    save_message(uid, session_id, "user", payload.message)
    history = load_messages(uid, 8, session_id)
    reply = chat_with_llama(history)
    save_message(uid, session_id, "assistant", reply)
    return {"reply": reply, "session_id": session_id, "session_title": session_title}

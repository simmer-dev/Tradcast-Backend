from fastapi import APIRouter, Request
import json
from utils.auth_utils import decrypt
from configs.config import SECRET

session_router = APIRouter()


@session_router.post("/start_session")
async def start_session(request: Request):
    body = await request.json()

    try:
        encrypted_token = body.get('encrypted_token')
        if not encrypted_token:
            return {"error": "No encrypted_token provided"}

        decrypted_json = decrypt(encrypted_token, SECRET)
        payload = json.loads(decrypted_json)

        return {"success": True, "payload": payload}

    except Exception as e:
        return {"error": str(e)}

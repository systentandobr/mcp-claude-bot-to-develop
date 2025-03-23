import time
import hmac
import hashlib
import json
from fastapi import Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.security import APIKeyHeader
from fastapi import Security
import os
from dotenv import load_dotenv
from security.encryption import encryption_manager

# Carrega variáveis de ambiente
load_dotenv()

# Configurações de segurança
MCP_API_KEY = os.getenv('MCP_API_KEY', '')
MAX_TIMESTAMP_DIFF = 300  # 5 minutos em segundos

# Esquema de autenticação de API Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Verifica se a API Key é válida."""
    if api_key_header != MCP_API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="API Key inválida ou não autorizada."
        )
    return api_key_header

class SecureMiddleware(BaseHTTPMiddleware):
    """Middleware para verificar autenticação e criptografia."""
    
    async def dispatch(self, request: Request, call_next):
        # Bypass para a rota de status/healthcheck
        if request.url.path == "/":
            return await call_next(request)
        
        try:
            # Verifica cabeçalhos de autenticação
            if "X-API-Key" not in request.headers:
                raise HTTPException(
                    status_code=401, 
                    detail="API Key não fornecida."
                )
            
            api_key = request.headers.get("X-API-Key")
            timestamp = request.headers.get("X-Timestamp")
            signature = request.headers.get("X-Signature")
            
            if not all([api_key, timestamp, signature]):
                raise HTTPException(
                    status_code=401, 
                    detail="Cabeçalhos de autenticação incompletos."
                )
            
            # Verifica se a API key é válida
            if api_key != MCP_API_KEY:
                raise HTTPException(
                    status_code=403, 
                    detail="API Key inválida."
                )
            
            # Verifica se o timestamp é recente
            current_time = int(time.time())
            request_time = int(timestamp)
            
            if abs(current_time - request_time) > MAX_TIMESTAMP_DIFF:
                raise HTTPException(
                    status_code=401, 
                    detail="Timestamp expirado ou inválido."
                )
            
            # Lê e armazena o corpo da requisição para verificação da assinatura
            body = await request.body()
            await request._body.seek(0)  # Redefine o cursor do body para o início
            
            # Verifica a assinatura
            body_dict = json.loads(body)
            message = f"{json.dumps(body_dict)}{timestamp}"
            expected_signature = hmac.new(
                MCP_API_KEY.encode(), 
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if signature != expected_signature:
                raise HTTPException(
                    status_code=403, 
                    detail="Assinatura inválida."
                )
            
            # Continua com a requisição
            response = await call_next(request)
            return response
            
        except HTTPException as http_ex:
            # Propaga exceções HTTP
            raise http_ex
        except Exception as e:
            # Captura outras exceções e retorna erro 500
            raise HTTPException(
                status_code=500, 
                detail=f"Erro interno: {str(e)}"
            )

# Funções auxiliares para criptografia e descriptografia

async def decrypt_request_data(request: Request):
    """Descriptografa os dados da requisição."""
    try:
        # Lê o corpo da requisição
        body = await request.json()
        
        if "encrypted_data" not in body:
            return {}
        
        # Descriptografa os dados
        encrypted_data = body.get("encrypted_data")
        if encrypted_data:
            decrypted_data = encryption_manager.decrypt_text(encrypted_data)
            return json.loads(decrypted_data) if decrypted_data else {}
        return {}
    except Exception as e:
        print(f"Erro ao descriptografar dados: {e}")
        return {}

def encrypt_response_data(data):
    """Criptografa os dados da resposta."""
    try:
        if not data:
            return {"encrypted_data": None}
        
        # Criptografa os dados
        data_str = json.dumps(data)
        encrypted_data = encryption_manager.encrypt_text(data_str)
        
        return {"encrypted_data": encrypted_data}
    except Exception as e:
        print(f"Erro ao criptografar dados: {e}")
        return {"error": "Erro ao criptografar dados de resposta"}

import time
import hmac
import hashlib
import json
import logging
from fastapi import Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.security import APIKeyHeader
from fastapi import Security
import os
from dotenv import load_dotenv
from security.encryption import encryption_manager
from utils.common import get_env_var, get_security_config, update_env_var

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carrega configurações de segurança
security_config = get_security_config()
MCP_API_KEY = security_config.get('mcp_api_key')

# Gera uma nova chave se não existir
if not MCP_API_KEY:
    import secrets
    MCP_API_KEY = secrets.token_hex(32)
    update_env_var('MCP_API_KEY', MCP_API_KEY)
    logger.info("Nova MCP_API_KEY gerada e salva no arquivo .env")

# Constantes e configurações
MAX_TIMESTAMP_DIFF = 300  # 5 minutos em segundos

# Lista de rotas permitidas sem autenticação
EXEMPTED_ROUTES = ["/", "/docs", "/openapi.json", "/health"]

# Esquema de autenticação de API Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Verifica se a API Key é válida."""
    if not api_key_header:
        raise HTTPException(
            status_code=401, 
            detail="API Key não fornecida."
        )
    
    if api_key_header != MCP_API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="API Key inválida ou não autorizada."
        )
    return api_key_header

class SecureMiddleware(BaseHTTPMiddleware):
    """Middleware para verificar autenticação e criptografia."""
    
    async def dispatch(self, request: Request, call_next):
        # Bypass para rotas específicas que não precisam de autenticação
        if request.url.path in EXEMPTED_ROUTES:
            return await call_next(request)
            
        try:
            logger.debug(f"Processando requisição para: {request.url.path}")
            
            # Verifica cabeçalhos de autenticação
            if "X-API-Key" not in request.headers:
                logger.warning(f"Tentativa de acesso sem API Key para {request.url.path}")
                raise HTTPException(
                    status_code=401, 
                    detail="API Key não fornecida."
                )
            
            api_key = request.headers.get("X-API-Key")
            timestamp = request.headers.get("X-Timestamp")
            signature = request.headers.get("X-Signature")
            
            if not all([api_key, timestamp, signature]):
                logger.warning(f"Cabeçalhos de autenticação incompletos para {request.url.path}")
                raise HTTPException(
                    status_code=401, 
                    detail="Cabeçalhos de autenticação incompletos."
                )
            
            # Verifica se a API key é válida
            if api_key != MCP_API_KEY:
                logger.warning(f"API Key inválida fornecida para {request.url.path}")
                raise HTTPException(
                    status_code=403, 
                    detail="API Key inválida."
                )
            
            # Verifica se o timestamp é recente
            try:
                current_time = int(time.time())
                request_time = int(timestamp)
                
                if abs(current_time - request_time) > MAX_TIMESTAMP_DIFF:
                    logger.warning(f"Timestamp expirado para {request.url.path}: {current_time} vs {request_time}")
                    raise HTTPException(
                        status_code=401, 
                        detail="Timestamp expirado ou inválido."
                    )
            except ValueError:
                raise HTTPException(
                    status_code=401,
                    detail="Timestamp inválido."
                )
            
            # Para requisições GET, verificamos apenas os parâmetros
            if request.method == "GET":
                # Para requisições GET, usamos os parâmetros da query
                params = dict(request.query_params)
                if "chat_id" in params and "timestamp" in params:
                    message = f"{json.dumps(params)}{timestamp}"
                    expected_signature = hmac.new(
                        MCP_API_KEY.encode(), 
                        message.encode(),
                        hashlib.sha256
                    ).hexdigest()
                    
                    if signature != expected_signature:
                        logger.warning(f"Assinatura inválida para {request.url.path}")
                        raise HTTPException(
                            status_code=403, 
                            detail="Assinatura inválida."
                        )
                else:
                    logger.warning(f"Parâmetros de query incompletos para {request.url.path}")
                    raise HTTPException(
                        status_code=400,
                        detail="Parâmetros requeridos não fornecidos."
                    )
            else:
                # Para POST/PUT/DELETE, verificamos o corpo da requisição
                try:
                    # Lê o corpo de forma segura
                    body_bytes = await request.body()
                    # Salva o corpo para ser lido novamente nas rotas
                    request._body = body_bytes
                    
                    try:
                        body_dict = json.loads(body_bytes.decode())
                        message = f"{json.dumps(body_dict)}{timestamp}"
                        expected_signature = hmac.new(
                            MCP_API_KEY.encode(),
                            message.encode(),
                            hashlib.sha256
                        ).hexdigest()
                        
                        if signature != expected_signature:
                            logger.warning(f"Assinatura inválida para {request.url.path}")
                            raise HTTPException(
                                status_code=403,
                                detail="Assinatura inválida."
                            )
                    except json.JSONDecodeError:
                        logger.error(f"Corpo da requisição inválido (não é JSON) para {request.url.path}")
                        raise HTTPException(
                            status_code=400,
                            detail="Corpo da requisição inválido. É esperado um objeto JSON."
                        )
                except Exception as e:
                    logger.error(f"Erro ao processar corpo da requisição: {str(e)}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Erro ao processar corpo da requisição: {str(e)}"
                    )
            
            # Continua com a requisição
            response = await call_next(request)
            return response
            
        except HTTPException as http_ex:
            # Propaga exceções HTTP
            logger.warning(f"Exceção HTTP em middleware: {http_ex.status_code} - {http_ex.detail}")
            raise http_ex
        except Exception as e:
            # Captura outras exceções e retorna erro 500
            logger.error(f"Erro interno no middleware: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Erro interno: {str(e)}"
            )

# Funções auxiliares para criptografia e descriptografia

async def decrypt_request_data(request: Request):
    """Descriptografa os dados da requisição."""
    try:
        # Lê o corpo da requisição
        body_bytes = await request.body()
        body = json.loads(body_bytes.decode())
        
        if "encrypted_data" not in body:
            return {}
        
        # Descriptografa os dados
        encrypted_data = body.get("encrypted_data")
        if encrypted_data:
            decrypted_data = encryption_manager.decrypt_text(encrypted_data)
            return json.loads(decrypted_data) if decrypted_data else {}
        return {}
    except Exception as e:
        logger.error(f"Erro ao descriptografar dados: {e}")
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
        logger.error(f"Erro ao criptografar dados: {e}")
        return {"error": "Erro ao criptografar dados de resposta"}
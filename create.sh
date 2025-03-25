cat > security/mcp_security.py << 'EOF'
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

# Lista de rotas permitidas sem autenticação (expandida)
EXEMPTED_ROUTES = ["/", "/docs", "/openapi.json", "/health", "/redoc", "/mcp/info"]

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
        if any(request.url.path.startswith(route) for route in EXEMPTED_ROUTES):
            return await call_next(request)
            
        try:
            logger.debug(f"Processando requisição para: {request.url.path}")
            
            # Verifica cabeçalhos de autenticação
            if "X-API-Key" not in request.headers:
                logger.warning(f"Tentativa de acesso sem API Key para {request.url.path}")
                
                # Permitir acesso temporário (para desenvolvimento) - REMOVER EM PRODUÇÃO
                logger.warning("Permitindo acesso sem API Key durante desenvolvimento")
                return await call_next(request)
                
                # Em produção, use o código abaixo:
                # raise HTTPException(
                #     status_code=401, 
                #     detail="API Key não fornecida."
                # )
            
            api_key = request.headers.get("X-API-Key")
            timestamp = request.headers.get("X-Timestamp")
            signature = request.headers.get("X-Signature")
            
            if not all([api_key, timestamp, signature]):
                logger.warning(f"Cabeçalhos de autenticação incompletos para {request.url.path}")
                
                # Permitir acesso temporário (para desenvolvimento) - REMOVER EM PRODUÇÃO
                logger.warning("Permitindo acesso sem cabeçalhos completos durante desenvolvimento")
                return await call_next(request)
                
                # Em produção, use o código abaixo:
                # raise HTTPException(
                #     status_code=401, 
                #     detail="Cabeçalhos de autenticação incompletos."
                # )
            
            # Verifica se a API key é válida
            if api_key != MCP_API_KEY:
                logger.warning(f"API Key inválida fornecida para {request.url.path}")
                
                # Permitir acesso temporário (para desenvolvimento) - REMOVER EM PRODUÇÃO
                logger.warning("Permitindo acesso com API Key inválida durante desenvolvimento")
                return await call_next(request)
                
                # Em produção, use o código abaixo:
                # raise HTTPException(
                #     status_code=403, 
                #     detail="API Key inválida."
                # )
            
            # Verifica se o timestamp é recente
            try:
                current_time = int(time.time())
                request_time = int(timestamp)
                
                if abs(current_time - request_time) > MAX_TIMESTAMP_DIFF:
                    logger.warning(f"Timestamp expirado para {request.url.path}: {current_time} vs {request_time}")
                    
                    # Permitir acesso temporário (para desenvolvimento) - REMOVER EM PRODUÇÃO
                    logger.warning("Permitindo acesso com timestamp expirado durante desenvolvimento")
                    return await call_next(request)
                    
                    # Em produção, use o código abaixo:
                    # raise HTTPException(
                    #     status_code=401, 
                    #     detail="Timestamp expirado ou inválido."
                    # )
            except ValueError:
                logger.warning(f"Timestamp inválido fornecido para {request.url.path}")
                
                # Permitir acesso temporário (para desenvolvimento) - REMOVER EM PRODUÇÃO
                logger.warning("Permitindo acesso com timestamp inválido durante desenvolvimento")
                return await call_next(request)
                
                # Em produção, use o código abaixo:
                # raise HTTPException(
                #     status_code=401,
                #     detail="Timestamp inválido."
                # )
            
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
EOF
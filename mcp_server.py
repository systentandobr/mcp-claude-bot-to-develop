import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from security.mcp_security import SecureMiddleware
from server_api import router as api_router
from utils.common import get_connection_config

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carrega configurações
connection_config = get_connection_config()
MCP_PORT = connection_config["mcp_port"]
MCP_HOST = connection_config["mcp_host"]


# Contexto de gerenciamento de eventos para inicialização e encerramento
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Código executado durante a inicialização
    logger.info("Iniciando servidor MCP...")

    # Registra evento de inicialização
    event = {
        "type": "system.startup",
        "timestamp": time.time(),
        "data": {"host": MCP_HOST, "port": MCP_PORT, "version": "1.0.0"},
    }
    logger.info(f"Evento MCP: {json.dumps(event)}")

    # Fornece aplicativo para o FastAPI
    yield

    # Código executado durante o encerramento
    logger.info("Encerrando servidor MCP...")

    # Registra evento de encerramento
    event = {
        "type": "system.shutdown",
        "timestamp": time.time(),
        "data": {"host": MCP_HOST, "port": MCP_PORT},
    }
    logger.info(f"Evento MCP: {json.dumps(event)}")


# Inicializa o aplicativo FastAPI com o gerenciador de ciclo de vida
app = FastAPI(
    title="MCP Server - Gerenciador de Repositório com IA",
    description="Servidor que implementa o padrão Model Context Protocol para gerenciar repositórios com IA",
    version="1.0.0",
    lifespan=lifespan,
)


# Middleware para capturar e registrar eventos
@app.middleware("http")
async def mcp_event_middleware(request: Request, call_next):
    # Registra evento de requisição recebida
    event = {
        "type": "request.received",
        "timestamp": time.time(),
        "data": {
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown",
        },
    }
    logger.info(f"Evento MCP: {json.dumps(event)}")

    # Processa a requisição
    start_time = time.time()
    try:
        response = await call_next(request)

        # Registra evento de resposta enviada
        event = {
            "type": "response.sent",
            "timestamp": time.time(),
            "data": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "processing_time": time.time() - start_time,
            },
        }
        logger.info(f"Evento MCP: {json.dumps(event)}")

        return response
    except Exception as e:
        # Registra evento de erro
        event = {
            "type": "error.occurred",
            "timestamp": time.time(),
            "data": {
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "processing_time": time.time() - start_time,
            },
        }
        logger.error(f"Evento MCP: {json.dumps(event)}")

        # Re-lança a exceção para ser tratada pelos handlers do FastAPI
        raise


# Aplica o middleware de segurança
app.add_middleware(SecureMiddleware)

# Inclui os endpoints da API
app.include_router(api_router)


# Endpoint MCP específico para eventos do sistema
@app.post("/mcp/events")
async def register_mcp_event(request: Request):
    """Endpoint para registrar eventos MCP externos."""
    try:
        # Extrai o evento do corpo da requisição
        event_data = await request.json()

        # Valida o formato do evento
        if not all(key in event_data for key in ["type", "timestamp", "data"]):
            raise HTTPException(
                status_code=400,
                detail="Formato de evento inválido. Deve conter 'type', 'timestamp' e 'data'",
            )

        # Registra o evento
        logger.info(f"Evento MCP Externo: {json.dumps(event_data)}")

        return {"status": "success", "message": "Evento registrado com sucesso"}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Formato JSON inválido")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao processar evento: {str(e)}"
        )


# Endpoint para recuperar eventos (simulado - em uma implementação real, seria conectado a um banco de dados)
@app.get("/mcp/events")
async def get_mcp_events(event_type: str = None, limit: int = 10):
    """Endpoint para recuperar eventos MCP (simulado)."""
    return {
        "status": "success",
        "message": "Esta é uma simulação. Em uma implementação real, este endpoint retornaria eventos do sistema.",
        "data": {"event_type": event_type, "limit": limit, "events": []},
    }


# Endpoint para informações sobre o MCP
@app.get("/mcp/info")
async def get_mcp_info():
    """Retorna informações sobre o servidor MCP."""
    return {
        "status": "success",
        "data": {
            "name": "Telegram Dev Bot MCP Server",
            "version": "1.0.0",
            "uptime": time.time(),  # Em uma implementação real, calcularia o tempo real de atividade
            "protocol": "MCP 1.0",
            "models_supported": ["claude-3-7-sonnet-20250219"],
            "features": ["repository_management", "code_suggestions", "git_operations"],
        },
    }


# Inicia a aplicação
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=MCP_HOST, port=int(MCP_PORT), log_level="info")

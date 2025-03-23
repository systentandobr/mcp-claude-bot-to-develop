# Servidor MCP (Master Control Program)
# O código completo será adicionado posteriormente
import os
from fastapi import FastAPI
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa a aplicação FastAPI
app = FastAPI(title="MCP Server - Gerenciador de Repositório com IA")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

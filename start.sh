#!/bin/bash

# Script de inicialização do sistema de desenvolvimento remoto via Telegram

# Carrega variáveis de ambiente
source .env

# Verifica se o diretório de repositórios existe
if [ ! -d "$REPOS_BASE_PATH" ]; then
    echo "Criando diretório de repositórios: $REPOS_BASE_PATH"
    mkdir -p "$REPOS_BASE_PATH"
fi

# Inicia o servidor MCP em segundo plano
echo "Iniciando o servidor MCP..."
python mcp_server.py &
MCP_PID=$!

# Aguarda o servidor iniciar
sleep 2

# Inicia o bot do Telegram
echo "Iniciando o bot do Telegram..."
python telegram_bot.py

# Função para encerrar os processos
function cleanup {
    echo "Encerrando processos..."
    kill $MCP_PID
    echo "Processos encerrados."
    exit 0
}

# Captura sinais para encerramento gracioso
trap cleanup SIGINT SIGTERM

# Aguarda o término dos processos
wait $MCP_PID

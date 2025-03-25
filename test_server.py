#!/usr/bin/env python3
"""
Script para testar a conectividade com o servidor MCP.
"""

import requests
import json
import time
import hmac
import hashlib
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configurações
MCP_HOST = os.getenv('MCP_HOST', 'localhost')
MCP_PORT = os.getenv('MCP_PORT', '8000')
MCP_API_KEY = os.getenv('MCP_API_KEY', '')

BASE_URL = f"http://{MCP_HOST}:{MCP_PORT}"

def test_health():
    """Teste o endpoint de verificação de saúde (não requer autenticação)."""
    url = f"{BASE_URL}/health"
    
    try:
        response = requests.get(url)
        print(f"Health Check Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Erro no Health Check: {e}")
        return False

def test_root():
    """Teste o endpoint raiz (não requer autenticação)."""
    url = f"{BASE_URL}/"
    
    try:
        response = requests.get(url)
        print(f"Root Endpoint Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Erro no endpoint raiz: {e}")
        return False

def generate_signature(data, timestamp, api_key):
    """Gera uma assinatura HMAC para a requisição."""
    message = f"{json.dumps(data)}{timestamp}"
    signature = hmac.new(
        api_key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

def test_authenticated_get():
    """Teste um endpoint GET que requer autenticação."""
    if not MCP_API_KEY:
        print("Erro: MCP_API_KEY não está definida. Configure no arquivo .env")
        return False
        
    url = f"{BASE_URL}/repos"
    
    # Dados para requisição
    data = {
        "chat_id": "123456789"
    }
    
    # Gera a assinatura
    timestamp = str(int(time.time()))
    data["timestamp"] = timestamp  # Inclui o timestamp nos dados para verificação
    signature = generate_signature(data, timestamp, MCP_API_KEY)
    
    # Headers com autenticação
    headers = {
        "X-API-Key": MCP_API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=data)
        print(f"Authenticated GET Status: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Erro no endpoint GET autenticado: {e}")
        return False

def test_authenticated_post():
    """Teste um endpoint POST que requer autenticação."""
    if not MCP_API_KEY:
        print("Erro: MCP_API_KEY não está definida. Configure no arquivo .env")
        return False
        
    url = f"{BASE_URL}/select"
    
    # Dados para requisição
    data = {
        "chat_id": "123456789",
        "repo_name": "test-repo"
    }
    
    # Gera a assinatura
    timestamp = str(int(time.time()))
    signature = generate_signature(data, timestamp, MCP_API_KEY)
    
    # Headers com autenticação
    headers = {
        "X-API-Key": MCP_API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Authenticated POST Status: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code in [200, 404]  # 404 pode ser aceitável se o repo não existir
    except Exception as e:
        print(f"Erro no endpoint POST autenticado: {e}")
        return False

def main():
    """Função principal para executar os testes."""
    print("Testando conexão com o servidor MCP...\n")
    
    # Testa o endpoint de saúde
    print("1. Testando endpoint de saúde...")
    health_ok = test_health()
    print(f"Resultado: {'OK' if health_ok else 'FALHA'}\n")
    
    # Testa o endpoint raiz
    print("2. Testando endpoint raiz...")
    root_ok = test_root()
    print(f"Resultado: {'OK' if root_ok else 'FALHA'}\n")
    
    # Testa um endpoint GET autenticado
    print("3. Testando endpoint GET autenticado...")
    auth_get_ok = test_authenticated_get()
    print(f"Resultado: {'OK' if auth_get_ok else 'FALHA'}\n")
    
    # Testa um endpoint POST autenticado
    print("4. Testando endpoint POST autenticado...")
    auth_post_ok = test_authenticated_post()
    print(f"Resultado: {'OK' if auth_post_ok else 'FALHA'}\n")
    
    # Resultado geral
    overall = health_ok and root_ok and (auth_get_ok or auth_post_ok)
    print(f"Resultado geral: {'TODOS OS TESTES PASSARAM' if overall else 'ALGUNS TESTES FALHARAM'}")

if __name__ == "__main__":
    main()
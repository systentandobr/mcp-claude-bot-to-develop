import requests
import json
import time
import hmac
import hashlib
import os
from security.encryption import encryption_manager
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

class SecureMCPClient:
    def __init__(self):
        self.base_url = f"http://{os.getenv('MCP_HOST', 'localhost')}:{os.getenv('MCP_PORT', '8000')}"
        self.api_key = os.getenv('MCP_API_KEY', '')
        
        if not self.api_key:
            # Gera uma chave API se não existir
            self.api_key = self._generate_api_key()
            self._save_api_key_to_env()
    
    def _generate_api_key(self):
        """Gera uma chave API aleatória."""
        import secrets
        return secrets.token_hex(32)
    
    def _save_api_key_to_env(self):
        """Salva a chave API no arquivo .env."""
        try:
            # Lê o arquivo .env existente
            env_content = []
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    env_content = f.readlines()
            
            # Procura pela linha MCP_API_KEY e a substitui
            key_line_found = False
            for i, line in enumerate(env_content):
                if line.startswith('MCP_API_KEY='):
                    env_content[i] = f'MCP_API_KEY={self.api_key}\n'
                    key_line_found = True
                    break
            
            # Se não encontrou, adiciona no final
            if not key_line_found:
                env_content.append(f'MCP_API_KEY={self.api_key}\n')
            
            # Escreve de volta no arquivo
            with open('.env', 'w') as f:
                f.writelines(env_content)
                
        except Exception as e:
            print(f"Erro ao salvar chave API: {e}")
    
    def _generate_signature(self, data, timestamp):
        """Gera uma assinatura HMAC para a requisição."""
        message = f"{json.dumps(data)}{timestamp}"
        signature = hmac.new(
            self.api_key.encode(), 
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _secure_request(self, method, endpoint, data=None):
        """Realiza uma requisição segura para o MCP server."""
        url = f"{self.base_url}{endpoint}"
        
        # Adiciona um timestamp para evitar ataques de replay
        timestamp = str(int(time.time()))
        
        # Criptografa os dados
        encrypted_data = None
        if data:
            if isinstance(data, dict):
                encrypted_data = encryption_manager.encrypt_text(json.dumps(data))
            else:
                encrypted_data = encryption_manager.encrypt_text(data)
        
        # Wrapper para dados criptografados
        payload = {
            "encrypted_data": encrypted_data,
            "timestamp": timestamp
        }
        
        # Gera a assinatura
        signature = self._generate_signature(payload, timestamp)
        
        # Headers com autenticação
        headers = {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
        
        try:
            # Faz a requisição
            if method.lower() == 'get':
                response = requests.get(url, headers=headers, params=payload)
            elif method.lower() == 'post':
                response = requests.post(url, headers=headers, json=payload)
            elif method.lower() == 'put':
                response = requests.put(url, headers=headers, json=payload)
            elif method.lower() == 'delete':
                response = requests.delete(url, headers=headers, json=payload)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")
            
            # Verifica se a resposta foi bem-sucedida
            response.raise_for_status()
            
            # Descriptografa a resposta
            if response.text:
                response_data = response.json()
                if "encrypted_data" in response_data:
                    decrypted_data = encryption_manager.decrypt_text(response_data["encrypted_data"])
                    return json.loads(decrypted_data) if decrypted_data else {}
                return response_data
            return {}
            
        except requests.exceptions.RequestException as e:
            print(f"Erro na requisição: {e}")
            return {"error": str(e)}
    
    # Métodos para cada endpoint do MCP
    
    def list_repos(self, chat_id):
        """Lista todos os repositórios disponíveis."""
        return self._secure_request('get', '/repos', {"chat_id": chat_id})
    
    def select_repo(self, chat_id, repo_name):
        """Seleciona um repositório para trabalhar."""
        data = {
            "chat_id": chat_id,
            "repo_name": repo_name
        }
        return self._secure_request('post', '/select', data)
    
    def get_status(self, chat_id, repo_name=None):
        """Verifica o status do repositório."""
        data = {
            "chat_id": chat_id
        }
        if repo_name:
            data["repo_name"] = repo_name
        return self._secure_request('get', '/status', data)
    
    def suggest_modification(self, chat_id, file_path, description, repo_name=None):
        """Solicita ao Claude sugestões para modificar um arquivo."""
        data = {
            "chat_id": chat_id,
            "file_path": file_path,
            "description": description
        }
        if repo_name:
            data["repo_name"] = repo_name
        return self._secure_request('post', '/suggest', data)

# Instância global
mcp_client = SecureMCPClient()

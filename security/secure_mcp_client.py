import requests
import json
import time
import hmac
import hashlib
import os
import logging
from dotenv import load_dotenv

# Importação corrigida - use o caminho relativo correto
from security.encryption import encryption_manager
from utils.common import get_env_var, get_connection_config

# Carrega variáveis de ambiente
load_dotenv()

logger = logging.getLogger(__name__)

class SecureMCPClient:
    def __init__(self):
        config = get_connection_config()
        self.base_url = f"http://{config['mcp_host']}:{config['mcp_port']}"
        self.api_key = config['mcp_api_key']
        
        if not self.api_key:
            # Gera uma chave API se não existir
            self.api_key = self._generate_api_key()
            self._save_api_key_to_env()
        
        logger.info(f"SecureMCPClient inicializado com base_url: {self.base_url}")
    
    def _generate_api_key(self):
        """Gera uma chave API aleatória."""
        import secrets
        return secrets.token_hex(32)
    
    def _save_api_key_to_env(self):
        """Salva a chave API no arquivo .env."""
        try:
            from utils.common import update_env_var
            update_env_var('MCP_API_KEY', self.api_key)
        except Exception as e:
            logger.error(f"Erro ao salvar chave API: {e}")
    
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
        logger.debug(f"Fazendo requisição {method} para {url}")
        
        # Adiciona um timestamp para evitar ataques de replay
        timestamp = str(int(time.time()))
        
        if method.lower() == 'get':
            # Para GET, usamos query params
            query_params = {}
            
            # Se data existe, adiciona aos parâmetros
            if data:
                query_params.update(data)
            
            # Adiciona o timestamp
            query_params['timestamp'] = timestamp
            
            # Gera a assinatura baseada nos query params
            signature = self._generate_signature(query_params, timestamp)
            
            # Headers com autenticação
            headers = {
                "X-API-Key": self.api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature,
                "Content-Type": "application/json"
            }
            
            logger.debug(f"GET {url} com params: {query_params}")
            
            try:
                response = requests.get(url, headers=headers, params=query_params)
                
                # Log da resposta para debug
                logger.debug(f"Resposta: {response.status_code} - {response.text[:100]}...")
                
                response.raise_for_status()
                
                # Descriptografa a resposta
                if response.text:
                    try:
                        response_data = response.json()
                        return response_data
                    except json.JSONDecodeError:
                        return {"error": "Resposta inválida do servidor"}
                return {}
                
            except requests.exceptions.HTTPError as e:
                logger.error(f"Erro HTTP na requisição GET: {e}")
                return {"error": str(e)}
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição GET: {e}")
                return {"error": str(e)}
        else:
            # Para outros métodos (POST, PUT, DELETE)
            payload = data if data else {}
            
            # Gera a assinatura
            signature = self._generate_signature(payload, timestamp)
            
            # Headers com autenticação
            headers = {
                "X-API-Key": self.api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature,
                "Content-Type": "application/json"
            }
            
            logger.debug(f"{method.upper()} {url} com payload: {payload}")
            
            try:
                # Faz a requisição
                if method.lower() == 'post':
                    response = requests.post(url, headers=headers, json=payload)
                elif method.lower() == 'put':
                    response = requests.put(url, headers=headers, json=payload)
                elif method.lower() == 'delete':
                    response = requests.delete(url, headers=headers, json=payload)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")
                
                # Log da resposta para debug
                logger.debug(f"Resposta: {response.status_code} - {response.text[:100]}...")
                
                # Verifica se a resposta foi bem-sucedida
                response.raise_for_status()
                
                # Descriptografa a resposta
                if response.text:
                    try:
                        response_data = response.json()
                        return response_data
                    except json.JSONDecodeError:
                        return {"error": "Resposta inválida do servidor"}
                return {}
                
            except requests.exceptions.HTTPError as e:
                logger.error(f"Erro HTTP na requisição {method.upper()}: {e}")
                return {"error": str(e)}
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição {method.upper()}: {e}")
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
    
    def apply_modification(self, chat_id, suggestion_id):
        """Aplica a sugestão proposta pelo Claude."""
        data = {
            "chat_id": chat_id,
            "suggestion_id": suggestion_id
        }
        return self._secure_request('post', '/apply', data)
    
    def reject_modification(self, chat_id, suggestion_id):
        """Rejeita a sugestão proposta pelo Claude."""
        data = {
            "chat_id": chat_id,
            "suggestion_id": suggestion_id
        }
        return self._secure_request('post', '/reject', data)
    
    def commit_changes(self, chat_id, message, repo_name=None):
        """Realiza commit das alterações."""
        data = {
            "chat_id": chat_id,
            "message": message
        }
        if repo_name:
            data["repo_name"] = repo_name
        return self._secure_request('post', '/commit', data)
    
    def push_changes(self, chat_id, repo_name=None):
        """Envia as alterações para o GitHub."""
        data = {
            "chat_id": chat_id
        }
        if repo_name:
            data["repo_name"] = repo_name
        return self._secure_request('post', '/push', data)
    
    # Métodos adicionais para navegação em arquivos
    
    def list_files(self, chat_id, path=""):
        """Lista arquivos e diretórios."""
        data = {
            "chat_id": chat_id,
            "path": path
        }
        return self._secure_request('get', '/ls', data)
    
    def change_directory(self, chat_id, path):
        """Navega para outro diretório."""
        data = {
            "chat_id": chat_id,
            "path": path
        }
        return self._secure_request('post', '/cd', data)
    
    def get_file_content(self, chat_id, file_path, args):
        """Obtém o conteúdo de um arquivo."""
        data = {
            "chat_id": chat_id,
            "args": args,
            "file_path": file_path
        }
        return self._secure_request('get', '/cat', data)
    
    def get_current_directory(self, chat_id):
        """Obtém o diretório atual."""
        data = {
            "chat_id": chat_id
        }
        return self._secure_request('get', '/pwd', data)
    
    def get_tree(self, chat_id, max_depth=2, args=""):
        """Obtém a estrutura de diretórios."""
        data = {
            "chat_id": chat_id,
            "args": args,
            "max_depth": max_depth
        }
        return self._secure_request('get', '/tree', data)
    
    def get_branches(self, chat_id):
        """Obtém as branches do repositório."""
        data = {
            "chat_id": chat_id
        }
        return self._secure_request('get', '/branch', data)
    
    def checkout_branch(self, chat_id, branch_name, args):
        """Faz checkout para uma branch."""
        data = {
            "chat_id": chat_id,
            "args": args,
            "branch_name": branch_name
        }
        return self._secure_request('post', '/checkout', data)

# Instância global
mcp_client = SecureMCPClient()
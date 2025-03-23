import os
from dotenv import load_dotenv
from typing import Dict, Set, List, Optional

# Carrega variáveis de ambiente
load_dotenv()

class UserAuth:
    def __init__(self):
        # Lista de IDs de chat autorizados
        self.authorized_users: Set[str] = set()
        self.admin_users: Set[str] = set()
        self.user_tokens: Dict[str, str] = {}  # token: user_id
        
        # Carrega usuários autorizados do .env
        self._load_authorized_users()
    
    def _load_authorized_users(self):
        """Carrega usuários autorizados das variáveis de ambiente."""
        # Formato: ID1,ID2,ID3
        auth_users = os.getenv('AUTHORIZED_USERS', '')
        if auth_users:
            self.authorized_users = set(auth_users.split(','))
        
        # Admin tem privilégios adicionais (como adicionar novos usuários)
        admin_user = os.getenv('ADMIN_USER', '')
        if admin_user:
            self.admin_users = set(admin_user.split(','))
            # Admins também são usuários autorizados
            self.authorized_users.update(self.admin_users)
    
    def is_authorized(self, user_id: str) -> bool:
        """Verifica se o usuário está autorizado."""
        return user_id in self.authorized_users
    
    def is_admin(self, user_id: str) -> bool:
        """Verifica se o usuário é administrador."""
        return user_id in self.admin_users
    
    def generate_invite_token(self, admin_id: str) -> Optional[str]:
        """Gera um token de convite para um novo usuário (apenas admins)."""
        if not self.is_admin(admin_id):
            return None
        
        # Gera um token aleatório
        import secrets
        token = secrets.token_urlsafe(16)
        
        # Armazena o token temporariamente
        self.user_tokens[token] = None
        
        return token
    
    def redeem_invite_token(self, token: str, user_id: str) -> bool:
        """Resgata um token de convite para autorizar um novo usuário."""
        if token not in self.user_tokens:
            return False
        
        # Autoriza o usuário
        self.authorized_users.add(user_id)
        
        # Remove o token usado
        del self.user_tokens[token]
        
        # Atualiza o arquivo .env (opcional)
        self._update_env_file()
        
        return True
    
    def _update_env_file(self):
        """Atualiza o arquivo .env com os usuários autorizados."""
        try:
            # Lê o arquivo .env existente
            with open('.env', 'r') as f:
                env_lines = f.readlines()
            
            # Procura a linha AUTHORIZED_USERS
            found = False
            for i, line in enumerate(env_lines):
                if line.startswith('AUTHORIZED_USERS='):
                    env_lines[i] = f"AUTHORIZED_USERS={','.join(self.authorized_users)}\n"
                    found = True
                    break
            
            # Se não encontrou, adiciona no final
            if not found:
                env_lines.append(f"AUTHORIZED_USERS={','.join(self.authorized_users)}\n")
            
            # Escreve de volta no arquivo
            with open('.env', 'w') as f:
                f.writelines(env_lines)
                
        except Exception as e:
            print(f"Erro ao atualizar arquivo .env: {e}")

# Instância global
user_auth = UserAuth()

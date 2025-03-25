import logging
import os
import secrets
from typing import Dict, List, Optional, Set

from utils.common import get_security_config, update_env_var

logger = logging.getLogger(__name__)


class UserAuth:
    def __init__(self):
        # Lista de IDs de chat autorizados
        self.authorized_users: Set[str] = set()
        self.admin_users: Set[str] = set()
        self.user_tokens: Dict[str, str] = {}  # token: user_id

        # Carrega usuários autorizados
        self._load_authorized_users()

    def _load_authorized_users(self):
        """Carrega usuários autorizados das configurações de segurança."""
        security_config = get_security_config()

        # Carrega usuários autorizados
        if security_config["authorized_users"]:
            self.authorized_users = set(
                filter(None, security_config["authorized_users"])
            )

        # Carrega administradores
        if security_config["admin_users"]:
            self.admin_users = set(filter(None, security_config["admin_users"]))
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

        # Atualiza o arquivo .env
        self._update_env_file()

        return True

    def _update_env_file(self):
        """Atualiza o arquivo .env com os usuários autorizados."""
        try:
            # Atualiza a lista de usuários autorizados
            auth_users_str = ",".join(self.authorized_users)
            update_env_var("AUTHORIZED_USERS", auth_users_str)

            # Atualiza a lista de administradores
            admin_users_str = ",".join(self.admin_users)
            update_env_var("ADMIN_USER", admin_users_str)
        except Exception as e:
            logger.error(f"Erro ao atualizar arquivo .env: {e}")


# Instância global
user_auth = UserAuth()

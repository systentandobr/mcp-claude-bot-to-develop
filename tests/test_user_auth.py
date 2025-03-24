import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Adiciona o diretório raiz ao path para importação
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importa o módulo para teste
from security.user_auth import UserAuth


class TestUserAuth:
    @pytest.fixture
    def mock_env(self):
        with patch.dict(
            os.environ, {"AUTHORIZED_USERS": "123456,789012", "ADMIN_USER": "123456"}
        ):
            yield

    def test_load_authorized_users(self, mock_env):
        auth = UserAuth()
        assert "123456" in auth.authorized_users
        assert "789012" in auth.authorized_users
        assert "123456" in auth.admin_users
        assert "789012" not in auth.admin_users

    def test_is_authorized(self, mock_env):
        auth = UserAuth()
        assert auth.is_authorized("123456") is True
        assert auth.is_authorized("789012") is True
        assert auth.is_authorized("999999") is False

    def test_is_admin(self, mock_env):
        auth = UserAuth()
        assert auth.is_admin("123456") is True
        assert auth.is_admin("789012") is False
        assert auth.is_admin("999999") is False

    def test_generate_invite_token(self, mock_env):
        auth = UserAuth()
        # Admin pode gerar token
        token = auth.generate_invite_token("123456")
        assert token is not None
        assert len(token) > 0
        assert token in auth.user_tokens

        # Não-admin não pode gerar token
        token = auth.generate_invite_token("789012")
        assert token is None

    def test_redeem_invite_token(self, mock_env):
        auth = UserAuth()

        # Gera um token para teste
        token = auth.generate_invite_token("123456")

        # Resgata o token com um novo usuário
        result = auth.redeem_invite_token(token, "555555")
        assert result is True
        assert "555555" in auth.authorized_users

        # Verifica que o token foi removido
        assert token not in auth.user_tokens

        # Tenta resgatar um token inválido
        result = auth.redeem_invite_token("invalid_token", "666666")
        assert result is False
        assert "666666" not in auth.authorized_users

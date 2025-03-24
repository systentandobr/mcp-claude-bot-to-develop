import base64
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Adiciona o diretório raiz ao path para importação
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importa o módulo para teste - com mock para evitar dependência de ambiente
with patch.dict(
    os.environ, {"ENCRYPTION_KEY": base64.urlsafe_b64encode(b"A" * 32).decode()}
):
    from security.encryption import EncryptionManager


class TestEncryptionManager:
    @pytest.fixture
    def encryption_manager(self):
        with patch.dict(
            os.environ, {"ENCRYPTION_KEY": base64.urlsafe_b64encode(b"A" * 32).decode()}
        ):
            manager = EncryptionManager()
            return manager

    def test_encrypt_decrypt_text(self, encryption_manager):
        # Texto original
        original_text = "Texto confidencial para teste"

        # Criptografa o texto
        encrypted_text = encryption_manager.encrypt_text(original_text)
        assert encrypted_text is not None
        assert encrypted_text != original_text

        # Descriptografa o texto
        decrypted_text = encryption_manager.decrypt_text(encrypted_text)
        assert decrypted_text == original_text

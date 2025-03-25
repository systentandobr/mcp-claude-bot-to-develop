import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils.common import get_env_var, update_env_var

logger = logging.getLogger(__name__)


class EncryptionManager:
    def __init__(self):
        # Gera ou carrega uma chave de criptografia
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)

    def _get_encryption_key(self):
        """Obtém a chave de criptografia do ambiente ou gera uma nova."""
        key_env = get_env_var("ENCRYPTION_KEY")

        if key_env:
            try:
                # Tenta usar a chave existente
                key = key_env.encode()
                # Validar se a chave está no formato correto
                Fernet(key)  # Isso lançará uma exceção se a chave não for válida
                return key
            except Exception as e:
                logger.warning(
                    f"Chave de criptografia existente é inválida: {e}. Gerando nova chave."
                )
                # Continua para gerar uma nova chave

        # Gera uma nova chave Fernet
        key = Fernet.generate_key()

        # Salva a chave no arquivo .env
        self._save_key_to_env(key.decode())

        return key

    def _save_key_to_env(self, key):
        """Salva a chave no arquivo .env."""
        try:
            # Usa a função de utilitário para atualizar a variável
            update_env_var("ENCRYPTION_KEY", key)
        except Exception as e:
            logger.error(f"Erro ao salvar chave de criptografia: {e}")

    def encrypt_text(self, text):
        """Criptografa um texto."""
        if not text:
            return None
        return self.cipher_suite.encrypt(text.encode()).decode()

    def decrypt_text(self, encrypted_text):
        """Descriptografa um texto."""
        if not encrypted_text:
            return None
        return self.cipher_suite.decrypt(encrypted_text.encode()).decode()

    def encrypt_file(self, file_path, output_path=None):
        """Criptografa um arquivo."""
        if output_path is None:
            output_path = file_path + ".encrypted"

        try:
            with open(file_path, "rb") as file:
                file_data = file.read()

            encrypted_data = self.cipher_suite.encrypt(file_data)

            with open(output_path, "wb") as file:
                file.write(encrypted_data)

            return output_path
        except Exception as e:
            logger.error(f"Erro ao criptografar arquivo: {e}")
            return None

    def decrypt_file(self, encrypted_file_path, output_path=None):
        """Descriptografa um arquivo."""
        if output_path is None:
            if encrypted_file_path.endswith(".encrypted"):
                output_path = encrypted_file_path[:-10]  # Remove .encrypted
            else:
                output_path = encrypted_file_path + ".decrypted"

        try:
            with open(encrypted_file_path, "rb") as file:
                encrypted_data = file.read()

            decrypted_data = self.cipher_suite.decrypt(encrypted_data)

            with open(output_path, "wb") as file:
                file.write(decrypted_data)

            return output_path
        except Exception as e:
            logger.error(f"Erro ao descriptografar arquivo: {e}")
            return None


# Instância global
encryption_manager = EncryptionManager()

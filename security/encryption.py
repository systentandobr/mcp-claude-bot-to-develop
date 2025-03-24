import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


class EncryptionManager:
    def __init__(self):
        # Gera ou carrega uma chave de criptografia
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)

    def _get_encryption_key(self):
        """Obtém a chave de criptografia do ambiente ou gera uma nova."""
        key_env = os.getenv("ENCRYPTION_KEY")

        if key_env:
            return key_env.encode()

        # Se não houver chave no ambiente, gera uma nova e salva
        password = os.urandom(32)  # Gera um "password" aleatório
        salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password))

        # Salva a chave no arquivo .env
        self._save_key_to_env(key.decode())

        return key

    def _save_key_to_env(self, key):
        """Salva a chave no arquivo .env."""
        try:
            # Lê o arquivo .env existente
            env_content = []
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    env_content = f.readlines()

            # Procura pela linha ENCRYPTION_KEY e a substitui
            key_line_found = False
            for i, line in enumerate(env_content):
                if line.startswith("ENCRYPTION_KEY="):
                    env_content[i] = f"ENCRYPTION_KEY={key}\n"
                    key_line_found = True
                    break

            # Se não encontrou, adiciona no final
            if not key_line_found:
                env_content.append(f"ENCRYPTION_KEY={key}\n")

            # Escreve de volta no arquivo
            with open(".env", "w") as f:
                f.writelines(env_content)

        except Exception as e:
            print(f"Erro ao salvar chave de criptografia: {e}")

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
            print(f"Erro ao criptografar arquivo: {e}")
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
            print(f"Erro ao descriptografar arquivo: {e}")
            return None


# Instância global
encryption_manager = EncryptionManager()

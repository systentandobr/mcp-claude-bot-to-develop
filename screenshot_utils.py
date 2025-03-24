import logging
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def capture_directory_structure(path, output_path=None, terminal_width=80):
    """
    Captura a estrutura de diretórios em uma imagem.
    Versão alternativa que não usa pyautogui.
    """
    try:
        if output_path is None:
            # Cria um arquivo temporário para a captura
            fd, output_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)

        # Gera texto da estrutura do diretório
        tree_output = generate_tree_text(path)

        # Cria uma imagem para mostrar a estrutura do diretório
        lines = tree_output.split("\n")
        font_size = 14
        line_height = font_size + 4
        height = len(lines) * line_height + 20
        width = terminal_width * (font_size // 2)  # Aproximação da largura do caractere

        # Cria a imagem
        img = Image.new("RGB", (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)

        # Desenha o texto
        y = 10
        for line in lines:
            # Cor padrão
            color = (200, 200, 200)

            # Cores simples para diretórios e arquivos
            if "└── " in line or "├── " in line:
                if line.endswith("/"):  # Diretório
                    color = (86, 156, 214)
                else:  # Arquivo
                    color = (212, 212, 212)

            draw.text((10, y), line, fill=color)
            y += line_height

        # Salva a imagem
        img.save(output_path)
        return output_path

    except Exception as e:
        logger.error(f"Erro ao capturar estrutura de diretório: {e}")
        return None


def generate_tree_text(path, prefix="", is_last=True, max_depth=3, current_depth=0):
    """
    Gera uma representação textual da estrutura de diretório.
    """
    if current_depth > max_depth:
        return ""

    base_name = os.path.basename(path)
    tree_text = prefix

    if is_last:
        tree_text += "└── "
        new_prefix = prefix + "    "
    else:
        tree_text += "├── "
        new_prefix = prefix + "│   "

    tree_text += base_name + ("\n" if os.path.isdir(path) else "")

    if os.path.isdir(path):
        try:
            items = sorted(os.listdir(path))
            # Filtra itens ocultos
            items = [item for item in items if not item.startswith(".")]

            for i, item in enumerate(items):
                item_path = os.path.join(path, item)
                is_last_item = i == len(items) - 1

                if os.path.isdir(item_path):
                    tree_text += generate_tree_text(
                        item_path,
                        new_prefix,
                        is_last_item,
                        max_depth,
                        current_depth + 1,
                    )
                else:
                    tree_text += new_prefix
                    if is_last_item:
                        tree_text += "└── "
                    else:
                        tree_text += "├── "
                    tree_text += item + "\n"
        except PermissionError:
            tree_text += new_prefix + "Permissão negada\n"

    return tree_text


def capture_file_content(file_path, output_path=None):
    """
    Captura o conteúdo de um arquivo em uma imagem.
    Versão alternativa que não usa pyautogui.
    """
    try:
        if output_path is None:
            # Cria um arquivo temporário para a captura
            fd, output_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)

        # Lê o conteúdo do arquivo
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()

        # Limita o tamanho do conteúdo para a visualização
        if len(content) > 5000:
            content = content[:5000] + "\n\n... (conteúdo truncado)"

        # Cria uma imagem para mostrar o conteúdo do arquivo
        lines = content.split("\n")
        font_size = 14
        line_height = font_size + 4
        height = len(lines) * line_height + 20
        width = max(80, max(len(line) for line in lines)) * (font_size // 2) + 20

        # Limita o tamanho da imagem
        height = min(height, 4000)
        width = min(width, 1200)

        # Cria a imagem
        img = Image.new("RGB", (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)

        # Desenha o texto
        y = 10
        for line in lines:
            if y >= height - line_height:
                break
            draw.text((10, y), line, fill=(200, 200, 200))
            y += line_height

        # Salva a imagem
        img.save(output_path)
        return output_path

    except Exception as e:
        logger.error(f"Erro ao capturar conteúdo do arquivo: {e}")
        return None

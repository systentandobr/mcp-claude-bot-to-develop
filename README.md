# Telegram Dev Bot com Claude AI

Uma solução segura para desenvolvimento remoto usando o Telegram como interface, permitindo manipular repositórios Git e receber sugestões de código do Claude AI sem a necessidade de uma IDE tradicional. Ideal para desenvolvedores que desejam aproveitar momentos de inspiração enquanto estão longe do computador.

## Características

- **Navegação entre múltiplos repositórios**: Alterne facilmente entre diferentes projetos
- **Visualização de arquivos**: Explore a estrutura de diretórios e conteúdo de arquivos
- **Capturas de tela**: Receba imagens da estrutura de diretórios e conteúdo de arquivos
- **Integração com Git**: Execute comandos Git comuns diretamente do Telegram
- **Sugestões de código IA**: Solicite ao Claude AI modificações em arquivos
- **Processo de validação**: Aprove ou rejeite sugestões antes de aplicá-las
- **Segurança avançada**: Autenticação, criptografia e proteção contra interceptação

## Recursos de Segurança

- **Sistema de autenticação** com controle de acesso baseado em usuários
- **Convites criptografados** para adicionar novos usuários ao sistema
- **Criptografia ponta-a-ponta** para a comunicação entre o bot e o servidor
- **Assinatura de requisições** para evitar ataques de interceptação
- **Proteção contra ataques de replay** usando timestamps e assinaturas
- **Registro detalhado** de todas as operações para auditoria

## Pré-requisitos

- Python 3.9+ 
- Conta no Telegram
- Token de bot do Telegram (obtenha através do [BotFather](https://t.me/botfather))
- Chave de API do Claude AI (Anthropic)
- Token de acesso pessoal do GitHub

## Instalação

1. Clone este repositório:
   ```bash
   git clone https://github.com/seu-usuario/telegram-dev-bot.git
   cd telegram-dev-bot
   ```

2. Execute o script de setup seguro:
   ```bash
   chmod +x setup-secure.sh
   ./setup-secure.sh
   ```

3. Configure as variáveis de ambiente copiando o arquivo `.env.example` para `.env` e preenchendo as informações necessárias:
   ```bash
   cp .env.example .env
   nano .env  # Edit the file with your API keys and paths
   ```

4. Torne o script de inicialização executável:
   ```bash
   chmod +x start.sh
   ```

## Uso

1. Inicie o bot e o servidor MCP:
   ```bash
   ./start.sh
   ```

2. Interaja com o bot no Telegram:
   - Envie `/start` para iniciar
   - Envie `/help` para ver todos os comandos disponíveis

### Fluxo de trabalho básico

1. Liste os repositórios disponíveis: `/repos`
2. Selecione um repositório: `/select nome_do_repo`
3. Navegue pelos diretórios: `/ls`, `/cd pasta`
4. Solicite uma sugestão de modificação: `/suggest arquivo.py "Adicionar validação de entrada"`
5. Revise a sugestão e aplique-a: `/apply 1`
6. Faça commit das alterações: `/commit "Adicionada validação de entrada"`
7. Envie as alterações para o GitHub: `/push`

## Comandos disponíveis

### Navegação
- `/repos` - Lista todos os repositórios disponíveis
- `/select <nome_repo>` - Seleciona um repositório para trabalhar
- `/ls [caminho]` - Lista arquivos e pastas do diretório atual ou do caminho especificado
- `/cd <caminho>` - Navega para o diretório especificado
- `/pwd` - Mostra o diretório atual
- `/tree [profundidade]` - Mostra a estrutura de diretórios (padrão: profundidade 2)
- `/cat <arquivo>` - Mostra o conteúdo de um arquivo

### Visualização
- `/screenshot [profundidade]` - Captura e envia uma imagem da estrutura de diretórios
- `/view <arquivo>` - Captura e envia uma imagem do conteúdo de um arquivo

### Manipulação de código
- `/status` - Verifica o status do repositório atual
- `/branch` - Mostra as branches do repositório
- `/checkout <branch>` - Muda para outra branch
- `/suggest <arquivo> <descrição>` - Solicita ao Claude sugestões para modificar um arquivo
- `/apply <id_sugestão>` - Aplica a sugestão proposta
- `/reject <id_sugestão>` - Rejeita a sugestão proposta
- `/commit <mensagem>` - Realiza commit das alterações
- `/push` - Envia as alterações para o GitHub

### Administração e segurança
- `/invite` - (Admin) Gera um token de convite para novos usuários
- `/join <token>` - Permite que um novo usuário se junte ao sistema
- `/users` - (Admin) Lista todos os usuários autorizados

## Cenários de Implantação

### Uso Pessoal
Configure o sistema em sua máquina local ou servidor pessoal para uso exclusivo.

### Pequenas Equipes
Implante como um servidor compartilhado com autenticação rigorosa e permissões por repositório.

### Ambiente Empresarial
Configure instâncias separadas para cada equipe ou departamento, com integração a sistemas de CI/CD e políticas de segurança corporativas.

## Segurança

O sistema inclui múltiplas camadas de segurança:

- **Autenticação de usuários** - Apenas usuários autorizados podem acessar o bot
- **Sistema de convites** - Administradores controlam quem pode se juntar
- **Comunicação criptografada** - Toda comunicação entre componentes é criptografada
- **Assinatura de mensagens** - Garante que as mensagens não sejam adulteradas
- **Proteção contra replay** - Evita ataques de repetição de requisições
- **Auditoria** - Registro detalhado de todas as operações

## Recomendações e Melhores Práticas

- Mantenha o acesso físico ao servidor protegido
- Use uma VPN para comunicação remota com o servidor
- Rotacione regularmente as chaves de API e tokens
- Faça backup regular da configuração e chaves
- Mantenha o sistema atualizado com as últimas correções de segurança

## Limitações

- O bot não suporta operações que requerem entrada interativa além de comandos simples
- Arquivos muito grandes podem não ser visualizados corretamente
- A captação de screenshot pode variar dependendo do ambiente onde o bot está sendo executado

## Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests.

## Licença

Este projeto está licenciado sob a licença MIT - veja o arquivo LICENSE para detalhes.
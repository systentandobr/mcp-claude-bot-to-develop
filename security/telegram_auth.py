from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from functools import wraps
from security.user_auth import user_auth

def restricted(func):
    """Decorador para restringir o uso de funções a usuários autorizados."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or "Sem username"
        
        if not user_auth.is_authorized(user_id):
            await update.message.reply_text(
                f"⚠️ Acesso negado. Seu ID ({user_id}) não está autorizado a usar este bot."
            )
            print(f"Tentativa de acesso não autorizado de {username} (ID: {user_id})")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    """Decorador para restringir o uso de funções a administradores."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id)
        
        if not user_auth.is_admin(user_id):
            await update.message.reply_text(
                "⚠️ Esta função é restrita a administradores."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# Comandos de autorização

@admin_only
async def generate_invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gera um token de convite para um novo usuário (apenas admin)."""
    admin_id = str(update.effective_user.id)
    token = user_auth.generate_invite_token(admin_id)
    
    if token:
        await update.message.reply_text(
            f"🔑 Token de convite gerado: `{token}`\n\n"
            f"Compartilhe este token com o usuário que você deseja adicionar.\n"
            f"Eles devem enviar o comando: /join {token}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Erro ao gerar token de convite.")

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Permite que um usuário se junte usando um token de convite."""
    if not context.args:
        await update.message.reply_text(
            "❌ Você precisa fornecer um token de convite.\n"
            "Uso: /join <token>"
        )
        return
    
    token = context.args[0]
    user_id = str(update.effective_user.id)
    
    if user_auth.is_authorized(user_id):
        await update.message.reply_text("✅ Você já está autorizado a usar este bot.")
        return
    
    success = user_auth.redeem_invite_token(token, user_id)
    
    if success:
        await update.message.reply_text(
            "🎉 Bem-vindo! Você agora está autorizado a usar este bot.\n"
            "Use /help para ver os comandos disponíveis."
        )
    else:
        await update.message.reply_text(
            "❌ Token de convite inválido ou expirado."
        )

@admin_only
async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista todos os usuários autorizados (apenas admin)."""
    users = user_auth.authorized_users
    admins = user_auth.admin_users
    
    message = "👥 **Usuários autorizados:**\n\n"
    
    for user_id in users:
        is_admin = user_id in admins
        message += f"- `{user_id}`" + (" (Admin)" if is_admin else "") + "\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# Registrar estes handlers no bot
def register_auth_handlers(application):
    application.add_handler(CommandHandler("invite", generate_invite_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("users", list_users_command))

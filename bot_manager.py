"""
Sentinel Host - Manager d'Hébergement de Bots Discord
Contrôlé via Bot Telegram
Auteur: Développé pour gestion multi-bots
Version: 3.1 (Correction NameError: logs_command, Ordre des fonctions)
"""

import os
import sys
import json
import subprocess
import psutil
import logging
import time
import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Tokens et IDs (À REMPLACER PAR VOS VRAIES VALEURS)
TELEGRAM_BOT_TOKEN = "8270775415:AAGnQszPyN4Nb5eCFQ-n0bNRUMQKJ2VWfzo" # Remplacez par votre token
ADMIN_CHAT_ID = 5770978800 # Remplacez par votre ID utilisateur Telegram
GITHUB_PAT = "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" # Token d'accès personnel GitHub (optionnel)

# Chemins du projet
BASE_DIR = Path(__file__).parent.resolve()
BOTS_DIR = BASE_DIR / "bots"
LOGS_DIR = BASE_DIR / "logs"
BACKUPS_DIR = BASE_DIR / "backups"
CONFIG_FILE = BASE_DIR / "sentinel_config.json"

# Configuration système
MAX_MEMORY_MB = 512  # Limite mémoire par bot
CHECK_INTERVAL = 30  # Intervalle de monitoring en secondes
MAX_RESTART_ATTEMPTS = 3  # Tentatives de redémarrage avant alerte

# États de conversation
(NEWBOT_NAME, NEWBOT_REPO,
 SETTOKEN_SELECT, SETTOKEN_VALUE,
 SETPREFIX_SELECT, SETPREFIX_VALUE,
 SETREPO_SELECT, SETREPO_VALUE, # L'erreur NameError venait de la non-définition de ces constantes
 EXECBOT_SELECT, EXECBOT_COMMAND,
 PIPINSTALL_SELECT, PIPINSTALL_PACKAGE,
 UPDATEBOT_SELECT) = range(13) # Ajustement du range pour inclure toutes les constantes


# ============================================================================
# INITIALISATION & UTILS
# ============================================================================

# Créer les dossiers nécessaires
for directory in [BOTS_DIR, LOGS_DIR, BACKUPS_DIR]:
    directory.mkdir(exist_ok=True)

# Configuration du logging
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Tenter de configurer stdout pour l'UTF-8 sur Windows
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'sentinel_host.log', encoding='utf-8'),
        stream_handler
    ]
)
logger = logging.getLogger('SentinelHost')


def check_admin(update: Update) -> bool:
    """Vérifie si l'utilisateur est l'administrateur configuré"""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        logger.warning(f"Tentative d'accès non autorisée de l'ID: {update.effective_chat.id}")
        return False
    return True


# ============================================================================
# GESTION DE LA CONFIGURATION
# ============================================================================

class ConfigManager:
    """Gestionnaire de configuration JSON pour les bots"""

    @staticmethod
    def load_config() -> Dict:
        """Charge la configuration depuis le fichier JSON"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Erreur chargement config: {e}")
                return {"bots": {}}
        return {"bots": {}}

    @staticmethod
    def save_config(config: Dict):
        """Sauvegarde la configuration dans le fichier JSON"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde config: {e}")

    @staticmethod
    def get_bot_config(bot_name: str) -> Optional[Dict]:
        """Récupère la configuration d'un bot spécifique"""
        config = ConfigManager.load_config()
        return config.get("bots", {}).get(bot_name)

    @staticmethod
    def update_bot_config(bot_name: str, updates: Dict):
        """Met à jour la configuration d'un bot"""
        config = ConfigManager.load_config()
        if "bots" not in config:
            config["bots"] = {}
        if bot_name not in config["bots"]:
            config["bots"][bot_name] = {}
        config["bots"][bot_name].update(updates)
        ConfigManager.save_config(config)

    @staticmethod
    def delete_bot_config(bot_name: str):
        """Supprime la configuration d'un bot"""
        config = ConfigManager.load_config()
        if bot_name in config.get("bots", {}):
            del config["bots"][bot_name]
            ConfigManager.save_config(config)


# ============================================================================
# GESTION DES PROCESSUS
# ============================================================================

class ProcessManager:
    """Gestionnaire de processus pour les bots Discord"""

    @staticmethod
    def _get_venv_python_path(bot_name: str) -> Path:
        """Détermine le chemin de l'exécutable Python dans le venv"""
        venv_dir = BOTS_DIR / bot_name / "venv"
        if platform.system() == "Windows":
            return venv_dir / "Scripts" / "python.exe"
        else:
            return venv_dir / "bin" / "python"

    @staticmethod
    def get_bot_process(bot_name: str) -> Optional[psutil.Process]:
        """Récupère le processus d'un bot par son nom et PID"""
        bot_config = ConfigManager.get_bot_config(bot_name)
        pid = bot_config.get("pid") if bot_config else None

        if not pid:
            return None

        try:
            process = psutil.Process(pid)
            if not process.is_running():
                 raise psutil.NoSuchProcess(pid)

            cmdline = process.cmdline()
            if not cmdline or str(BOTS_DIR / bot_name) not in ' '.join(cmdline):
                 return None

            return process

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            if bot_config and bot_config.get("status") == "running":
                ConfigManager.update_bot_config(bot_name, {"pid": None, "status": "stopped"})
            return None


    @staticmethod
    def start_bot(bot_name: str) -> tuple[bool, str]:
        """Démarre un bot Discord"""
        bot_dir = BOTS_DIR / bot_name
        bot_config = ConfigManager.get_bot_config(bot_name)

        if not bot_config:
            return False, "❌ Bot non configuré. Utilisez /newbot."

        if not bot_dir.exists():
            return False, "❌ Dossier du bot introuvable. Exécutez /setup."

        if ProcessManager.get_bot_process(bot_name):
            return False, "⚠️ Bot déjà en cours d'exécution."

        # Trouver le script principal
        main_file = bot_dir / (bot_config.get("main_file", "main.py"))
        if not main_file.exists():
            for name in ["bot.py", "main.py", "run.py", f"{bot_name}.py"]:
                test_file = bot_dir / name
                if test_file.exists():
                    main_file = test_file
                    ConfigManager.update_bot_config(bot_name, {"main_file": name})
                    break
            else:
                return False, "❌ Fichier principal (main.py, bot.py...) introuvable."

        # Chemin du Python du venv
        venv_python = ProcessManager._get_venv_python_path(bot_name)
        if not venv_python.exists():
            return False, "❌ Environnement virtuel introuvable. Exécutez /setup d'abord."

        # Log file
        log_file = LOGS_DIR / f"{bot_name}.log"

        try:
            command = [str(venv_python), str(main_file)]

            with open(log_file, 'a', encoding='utf-8') as log:
                if platform.system() == "Windows":
                    process = subprocess.Popen(
                        command,
                        cwd=str(bot_dir),
                        stdout=log,
                        stderr=log,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    process = subprocess.Popen(
                        command,
                        cwd=str(bot_dir),
                        stdout=log,
                        stderr=log,
                        start_new_session=True
                    )

            ConfigManager.update_bot_config(bot_name, {
                "pid": process.pid,
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "restart_count": 0
            })

            logger.info(f"Bot {bot_name} démarré (PID: {process.pid})")
            return True, f"✅ Bot démarré avec succès\n📊 PID: {process.pid}"

        except Exception as e:
            logger.error(f"Erreur démarrage {bot_name}: {e}", exc_info=True)
            return False, f"❌ Erreur: {str(e)}"

    @staticmethod
    def stop_bot(bot_name: str) -> tuple[bool, str]:
        """Arrête un bot Discord"""
        process = ProcessManager.get_bot_process(bot_name)

        if not process:
            ConfigManager.update_bot_config(bot_name, {"pid": None, "status": "stopped"})
            return False, "⚠️ Bot non en cours d'exécution."

        try:
            process.terminate()
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                logger.warning(f"Bot {bot_name} ne s'arrête pas, forcement (KILL)")
                process.kill()

            ConfigManager.update_bot_config(bot_name, {
                "pid": None,
                "status": "stopped",
                "stopped_at": datetime.now().isoformat()
            })

            logger.info(f"Bot {bot_name} arrêté")
            return True, "✅ Bot arrêté avec succès."

        except Exception as e:
            logger.error(f"Erreur arrêt {bot_name}: {e}")
            return False, f"❌ Erreur lors de l'arrêt: {str(e)}"

    @staticmethod
    def restart_bot(bot_name: str) -> tuple[bool, str]:
        """Redémarre un bot Discord"""
        success, msg = ProcessManager.stop_bot(bot_name)
        if not success and "non en cours" not in msg:
            return False, msg

        time.sleep(2)

        return ProcessManager.start_bot(bot_name)

    @staticmethod
    def get_bot_stats(bot_name: str) -> Optional[Dict]:
        """Récupère les statistiques d'un bot"""
        process = ProcessManager.get_bot_process(bot_name)

        if not process:
            return None

        try:
            return {
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "threads": process.num_threads(),
                "status": process.status(),
                "create_time": datetime.fromtimestamp(process.create_time())
            }
        except Exception as e:
            logger.error(f"Erreur stats {bot_name}: {e}")
            return None


# ============================================================================
# SETUP ET INSTALLATION
# ============================================================================

class BotSetup:
    """Gestionnaire de setup et installation des bots"""

    @staticmethod
    def _get_venv_pip_path(bot_name: str) -> Path:
        """Détermine le chemin de l'exécutable pip dans le venv"""
        venv_dir = BOTS_DIR / bot_name / "venv"
        if platform.system() == "Windows":
            return venv_dir / "Scripts" / "pip.exe"
        else:
            return venv_dir / "bin" / "pip"

    @staticmethod
    def install_dependencies_iterative(bot_name: str) -> tuple[bool, str]:
        """
        Installe les dépendances une par une pour éviter l'erreur Windows
        """
        bot_dir = BOTS_DIR / bot_name
        requirements_file = bot_dir / "requirements.txt"

        if not requirements_file.exists():
            return True, "ℹ️ Pas de requirements.txt trouvé."

        pip_path = BotSetup._get_venv_pip_path(bot_name)
        if not pip_path.exists():
            return False, "❌ Pip introuvable dans le venv. Exécutez /setup."

        try:
            with open(requirements_file, 'r') as f:
                packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            return False, f"❌ Erreur lecture requirements.txt: {e}"

        if not packages:
            return True, "ℹ️ Aucun package à installer."

        logger.info(f"Installation de {len(packages)} packages pour {bot_name}...")
        failed_packages = []
        success_count = 0

        for package in packages:
            try:
                result = subprocess.run(
                    [str(pip_path), "install", package],
                    cwd=str(bot_dir),
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode == 0:
                    success_count += 1
                else:
                    failed_packages.append(package)
                    logger.error(f"✗ {package} échoué: {result.stderr[:100]}")

            except subprocess.TimeoutExpired:
                failed_packages.append(package)
                logger.error(f"✗ {package} timeout")
            except Exception as e:
                failed_packages.append(package)
                logger.error(f"✗ {package} erreur: {e}")

        if failed_packages:
            return False, f"⚠️ {success_count}/{len(packages)} installés.\n❌ Échecs: {', '.join(failed_packages)}"
        else:
            return True, f"✅ Tous les packages installés ({success_count}/{len(packages)})."

    @staticmethod
    def clone_repository(bot_name: str, repo_url: str) -> tuple[bool, str]:
        """Clone un dépôt GitHub"""
        bot_dir = BOTS_DIR / bot_name

        if bot_dir.exists():
            if not (bot_dir / ".git").exists():
                 if not os.listdir(bot_dir):
                    shutil.rmtree(bot_dir)
                 else:
                    return False, "❌ Un dossier avec ce nom existe et n'est pas vide/un repo git."


        try:
            final_repo_url = repo_url
            if GITHUB_PAT and "github.com" in repo_url:
                if repo_url.startswith("https://"):
                    final_repo_url = repo_url.replace("https://", f"https://{GITHUB_PAT}@")

            result = subprocess.run(
                ["git", "clone", final_repo_url, str(bot_dir)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                return False, f"❌ Erreur git: {result.stderr}"

            return True, "✅ Dépôt cloné avec succès."

        except subprocess.TimeoutExpired:
            return False, "❌ Timeout lors du clonage."
        except FileNotFoundError:
            return False, "❌ Git n'est pas installé sur le système."
        except Exception as e:
            return False, f"❌ Erreur: {str(e)}"

    @staticmethod
    def pull_repository(bot_name: str) -> tuple[bool, str]:
        """Exécute un git pull pour mettre à jour le code"""
        bot_dir = BOTS_DIR / bot_name

        if not (bot_dir / ".git").exists():
             return False, "❌ Le dossier n'est pas un dépôt Git (manque .git)."

        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(bot_dir),
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                return False, f"❌ Erreur git pull: {result.stderr}"

            output = result.stdout.strip()
            if "Already up to date" in output:
                return True, "✅ Dépôt déjà à jour."

            return True, f"✅ Dépôt mis à jour avec succès.\n\nRésultat:\n```\n{output}\n```"

        except subprocess.TimeoutExpired:
            return False, "❌ Timeout lors du pull Git."
        except Exception as e:
            return False, f"❌ Erreur lors du pull Git: {str(e)}"


    @staticmethod
    def create_venv(bot_name: str) -> tuple[bool, str]:
        """Crée un environnement virtuel"""
        bot_dir = BOTS_DIR / bot_name
        venv_dir = bot_dir / "venv"

        if venv_dir.exists():
            return True, "ℹ️ Venv existe déjà."

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                timeout=120
            )

            pip_path = BotSetup._get_venv_pip_path(bot_name)
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip"],
                timeout=120
            )

            return True, "✅ Environnement virtuel créé."

        except Exception as e:
            return False, f"❌ Erreur création venv: {str(e)}"

    @staticmethod
    def setup_bot(bot_name: str) -> tuple[bool, str]:
        """Setup complet d'un bot"""
        bot_config = ConfigManager.get_bot_config(bot_name)
        if not bot_config:
            return False, "❌ Bot non configuré."

        messages = []
        is_success = True

        # 1. Cloner le repo si nécessaire (uniquement si le dossier n'existe pas)
        bot_dir = BOTS_DIR / bot_name
        repo_url = bot_config.get("github_repo")
        if repo_url and not bot_dir.exists():
            success, msg = BotSetup.clone_repository(bot_name, repo_url)
            messages.append(msg)
            if not success:
                is_success = False

        # 2. Créer le venv
        success, msg = BotSetup.create_venv(bot_name)
        messages.append(msg)
        if not success:
            is_success = False

        # 3. Installer les dépendances (itératif)
        success, msg = BotSetup.install_dependencies_iterative(bot_name)
        messages.append(msg)
        if not success:
            is_success = False

        # 4. Créer/mettre à jour .env
        token = bot_config.get("token")
        if token:
            env_file = bot_dir / ".env"
            try:
                bot_dir.mkdir(exist_ok=True)
                with open(env_file, 'w') as f:
                    f.write(f"DISCORD_TOKEN={token}\n")
                messages.append("✅ Fichier .env créé/mis à jour.")
            except Exception as e:
                messages.append(f"⚠️ Erreur création/mise à jour .env: {e}")
                is_success = False
        else:
             messages.append("⚠️ Token Discord non configuré. Fichier .env non créé. Utilisez /settoken.")


        ConfigManager.update_bot_config(bot_name, {"setup_completed": is_success})

        return is_success, "\n".join(messages)


# ============================================================================
# MONITORING
# ============================================================================

class BotMonitor:
    """Système de monitoring des bots"""

    @staticmethod
    async def monitor_loop(context: ContextTypes.DEFAULT_TYPE):
        """Boucle de monitoring principal"""
        config = ConfigManager.load_config()

        for bot_name, bot_config in config.get("bots", {}).items():
            if bot_config.get("status") != "running":
                continue

            process = ProcessManager.get_bot_process(bot_name)

            # Bot crashé (le get_bot_process a mis à jour le statut en 'stopped')
            if not process:
                restart_count = bot_config.get("restart_count", 0)

                if restart_count < MAX_RESTART_ATTEMPTS:
                    logger.warning(f"Bot {bot_name} crashé, redémarrage automatique...")
                    success, msg = ProcessManager.start_bot(bot_name)

                    if success:
                        ConfigManager.update_bot_config(bot_name, {
                            "restart_count": restart_count + 1
                        })
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"⚠️ Bot **{bot_name}** redémarré automatiquement.\n"
                                 f"Tentative **{restart_count + 1}/{MAX_RESTART_ATTEMPTS}**",
                            parse_mode='Markdown'
                        )
                else:
                    ConfigManager.update_bot_config(bot_name, {"status": "failed"})
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"🚨 ALERTE: Bot **{bot_name}** a échoué après {MAX_RESTART_ATTEMPTS} tentatives "
                             f"et a été marqué comme **failed**.",
                        parse_mode='Markdown'
                    )
                continue

            # Vérifier la mémoire (uniquement si le bot est en cours d'exécution)
            try:
                stats = ProcessManager.get_bot_stats(bot_name)
                if stats and stats["memory_mb"] > MAX_MEMORY_MB:
                    logger.warning(f"Bot {bot_name} dépasse la limite mémoire ({MAX_MEMORY_MB}MB)")

                    ProcessManager.stop_bot(bot_name)

                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"⚠️ ALERTE MÉMOIRE: Bot **{bot_name}** utilisait **{stats['memory_mb']:.0f}MB**.\n"
                             f"Il a été **arrêté** pour éviter un crash du VPS.",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Erreur monitoring {bot_name}: {e}")


# ============================================================================
# COMMANDES TELEGRAM - BASIQUES
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    if not check_admin(update): return

    welcome_msg = """
🛡️ **Sentinel Host** - Manager de Bots Discord

📋 **Commandes disponibles:**

**Gestion:**
/newbot - Créer un nouveau bot
/setup - Installer/configurer un bot
/updatebot - Mettre à jour le code du bot et redémarrer 🔄
/deletebot - Supprimer un bot

**Contrôle:**
/startbot - Démarrer un bot (liste les arrêtés)
/stopbot - Arrêter un bot (liste les actifs)
/restartbot - Redémarrer un bot (liste les actifs)

**Configuration:**
/settoken - Définir le token Discord
/setprefix - Définir le préfixe
/setrepo - Définir le dépôt GitHub

**Monitoring:**
/status - État de tous les bots
/health - Santé détaillée d'un bot
/logs - Voir les logs d'un bot

**Avancé:**
/execbot - Exécuter une commande shell
/pipinstall - Installer un package Python
"""
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    if not check_admin(update): return

    await update.message.reply_text(
        "📖 Pour plus d'informations, utilisez **/start** ou consultez le README.",
        parse_mode='Markdown'
    )


# ============================================================================
# COMMANDES TELEGRAM - STATUS & LOGS
# ============================================================================

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /status - Affiche l'état de tous les bots"""
    if not check_admin(update): return

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return

    status_msg = "📊 **État des Bots**\n\n"

    for bot_name, bot_config in bots.items():
        process = ProcessManager.get_bot_process(bot_name)

        if process:
            stats = ProcessManager.get_bot_stats(bot_name)
            status_msg += f"🟢 **{bot_name}**"
            if stats:
                status_msg += f" (CPU: {stats['cpu_percent']:.1f}%, RAM: {stats['memory_mb']:.0f}MB, PID: {process.pid})"
            status_msg += "\n"
        else:
            status = bot_config.get("status", "unknown")
            if status == "stopped":
                emoji = "🔴"
            elif status == "failed":
                emoji = "🚨"
            else:
                emoji = "⚠️"
            status_msg += f"{emoji} **{bot_name}** - **{status.upper()}**\n"

    await update.message.reply_text(status_msg, parse_mode='Markdown')


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /health - Santé détaillée d'un bot"""
    if not check_admin(update): return

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"health_{name}")]
                for name in bots.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🏥 Sélectionnez un bot pour voir sa santé:",
        reply_markup=reply_markup
    )


async def health_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour la santé d'un bot"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("health_", "")
    bot_config = ConfigManager.get_bot_config(bot_name)

    if not bot_config:
        await query.edit_message_text("❌ Bot introuvable.")
        return

    process = ProcessManager.get_bot_process(bot_name)

    health_msg = f"🏥 **Santé: {bot_name}**\n\n"

    if process:
        stats = ProcessManager.get_bot_stats(bot_name)
        health_msg += "✅ **État:** En ligne\n"
        health_msg += f"🆔 **PID:** {process.pid}\n"

        if stats:
            uptime = datetime.now() - stats['create_time']
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{days}j {hours}h {minutes}m"

            health_msg += f"💻 **CPU:** {stats['cpu_percent']:.1f}%\n"
            health_msg += f"🧠 **RAM:** {stats['memory_mb']:.0f}MB / {MAX_MEMORY_MB}MB\n"
            health_msg += f"🧵 **Threads:** {stats['threads']}\n"
            health_msg += f"⏱️ **Uptime:** {uptime_str}\n"

            if stats['memory_mb'] > MAX_MEMORY_MB * 0.8:
                health_msg += "\n⚠️ Utilisation mémoire élevée."
    else:
        status = bot_config.get("status", "unknown")
        health_msg += f"🔴 **État:** {status.upper()}\n"
        health_msg += f"🔄 **Tentatives:** {bot_config.get('restart_count', 0)}/{MAX_RESTART_ATTEMPTS}\n"

    health_msg += f"\n⚙️ **Configuration:**\n"
    health_msg += f"Préfixe: **{bot_config.get('prefix', 'N/A')}**\n"
    health_msg += f"Setup: {'✅ Complété' if bot_config.get('setup_completed') else '❌ Incomplet'}\n"
    health_msg += f"Repo: `{bot_config.get('github_repo', 'N/A')}`"

    await query.edit_message_text(health_msg, parse_mode='Markdown')

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /logs"""
    if not check_admin(update): return

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"logs_{name}")]
                for name in bots.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 Sélectionnez un bot pour voir ses logs:",
        reply_markup=reply_markup
    )


async def logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour afficher les logs"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("logs_", "")
    log_file = LOGS_DIR / f"{bot_name}.log"

    if not log_file.exists():
        await query.edit_message_text(f"❌ Pas de logs trouvés pour **{bot_name}**.", parse_mode='Markdown')
        return

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-50:] if len(lines) > 50 else lines
            log_content = ''.join(last_lines)

        if len(log_content) > 3500:
            log_content = "...\n" + log_content[-3500:]

        await query.edit_message_text(
            f"📋 **Logs: {bot_name}**\n\n```\n{log_content}\n```",
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Erreur lecture logs: {e}")


# ============================================================================
# COMMANDES TELEGRAM - CONTRÔLE
# ============================================================================

def _get_control_keyboard(status_filter: str) -> Optional[InlineKeyboardMarkup]:
    """Utilité pour générer le clavier des commandes de contrôle"""
    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    filtered_bots = {}
    for name, bot_config in bots.items():
        is_running = ProcessManager.get_bot_process(name) is not None
        if status_filter == "start" and not is_running:
            filtered_bots[name] = bot_config
        elif (status_filter == "stop" or status_filter == "restart") and is_running:
            filtered_bots[name] = bot_config

    if not filtered_bots:
        return None

    keyboard = [[InlineKeyboardButton(name, callback_data=f"{status_filter}_{name}")]
                for name in filtered_bots.keys()]
    return InlineKeyboardMarkup(keyboard)

async def startbot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /startbot"""
    if not check_admin(update): return

    reply_markup = _get_control_keyboard("start")

    if not reply_markup:
        await update.message.reply_text("ℹ️ Aucun bot à démarrer (ils sont tous actifs ou non configurés).")
        return

    await update.message.reply_text(
        "▶️ Sélectionnez un bot **arrêté** à démarrer:",
        reply_markup=reply_markup
    )


async def startbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour démarrer un bot"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("start_", "")
    await query.edit_message_text(f"⏳ Démarrage de **{bot_name}**...", parse_mode='Markdown')

    success, msg = ProcessManager.start_bot(bot_name)
    await query.edit_message_text(f"**{bot_name}**\n\n{msg}", parse_mode='Markdown')


async def stopbot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /stopbot"""
    if not check_admin(update): return

    reply_markup = _get_control_keyboard("stop")

    if not reply_markup:
        await update.message.reply_text("ℹ️ Aucun bot à arrêter (ils sont tous arrêtés ou non configurés).")
        return

    await update.message.reply_text(
        "⏹️ Sélectionnez un bot **actif** à arrêter:",
        reply_markup=reply_markup
    )


async def stopbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour arrêter un bot"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("stop_", "")
    await query.edit_message_text(f"⏳ Arrêt de **{bot_name}**...", parse_mode='Markdown')

    success, msg = ProcessManager.stop_bot(bot_name)
    await query.edit_message_text(f"**{bot_name}**\n\n{msg}", parse_mode='Markdown')


async def restartbot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /restartbot"""
    if not check_admin(update): return

    reply_markup = _get_control_keyboard("restart")

    if not reply_markup:
        await update.message.reply_text("ℹ️ Aucun bot à redémarrer (ils sont tous arrêtés ou non configurés).")
        return

    await update.message.reply_text(
        "🔄 Sélectionnez un bot **actif** à redémarrer:",
        reply_markup=reply_markup
    )


async def restartbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour redémarrer un bot"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("restart_", "")
    await query.edit_message_text(f"⏳ Redémarrage de **{bot_name}**...", parse_mode='Markdown')

    success, msg = ProcessManager.restart_bot(bot_name)
    await query.edit_message_text(f"**{bot_name}**\n\n{msg}", parse_mode='Markdown')


# ============================================================================
# COMMANDES TELEGRAM - SETUP & GESTION
# ============================================================================

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /setup"""
    if not check_admin(update): return

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré. Utilisez /newbot.")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"setup_{name}")]
                for name in bots.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ Sélectionnez un bot à installer/configurer:",
        reply_markup=reply_markup
    )


async def setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour setup"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("setup_", "")
    await query.edit_message_text(f"⏳ Installation de **{bot_name}**...\nCela peut prendre plusieurs minutes.", parse_mode='Markdown')

    success, msg = BotSetup.setup_bot(bot_name)

    final_msg = f"**Setup: {bot_name}**\n\n{msg}"
    if success:
        final_msg += "\n\n✅ Setup terminé! Vous pouvez maintenant utiliser /startbot."

    await query.edit_message_text(final_msg, parse_mode='Markdown')


async def updatebot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /updatebot - Démarre la conversation de mise à jour"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    # Filtrer pour n'afficher que les bots avec un dépôt GitHub configuré
    updatable_bots = {
        name: config for name, config in bots.items() if config.get("github_repo")
    }

    if not updatable_bots:
        await update.message.reply_text("ℹ️ Aucun bot avec un dépôt GitHub configuré pour la mise à jour.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"update_{name}")]
                for name in updatable_bots.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔄 Sélectionnez le bot à mettre à jour (Git Pull + Re-Setup + Redémarrage):",
        reply_markup=reply_markup
    )
    return UPDATEBOT_SELECT

async def updatebot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour lancer la mise à jour"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("update_", "")
    bot_config = ConfigManager.get_bot_config(bot_name)

    if not bot_config or not bot_config.get("github_repo"):
        await query.edit_message_text(f"❌ Impossible de mettre à jour **{bot_name}**: Le dépôt GitHub est manquant.")
        return ConversationHandler.END

    await query.edit_message_text(f"⏳ **Mise à jour de {bot_name} en cours...**\n(Git Pull)", parse_mode='Markdown')

    # 1. Tenter un Git Pull
    pull_success, pull_msg = BotSetup.pull_repository(bot_name)
    update_messages = [pull_msg]

    # 2. Réexécuter le Setup complet (pour mettre à jour venv/dépendances)
    setup_success = False
    if pull_success:
        await query.edit_message_text(f"⏳ **Mise à jour de {bot_name} en cours...**\n(Réinstallation des dépendances)", parse_mode='Markdown')
        setup_success, setup_msg = BotSetup.setup_bot(bot_name)
        update_messages.append(setup_msg)

    # 3. Redémarrer le bot et nettoyer
    if pull_success and setup_success:
        await query.edit_message_text(f"⏳ **Mise à jour de {bot_name} en cours...**\n(Redémarrage)", parse_mode='Markdown')

        # Arrêter le bot avant de le redémarrer
        ProcessManager.stop_bot(bot_name)

        restart_success, restart_msg = ProcessManager.start_bot(bot_name)
        update_messages.append(restart_msg)

        if restart_success:
            final_msg = f"✅ **Mise à jour complète et Redémarrage réussis pour {bot_name}.**\n\n"
        else:
            final_msg = f"⚠️ **Mise à jour du code réussie, mais échec du Redémarrage.**\n\n"
    elif pull_success and not setup_success:
         final_msg = f"❌ **Mise à jour du code réussie, mais échec du Re-Setup (Venv/Dépendances).**\n"
    else:
        final_msg = f"❌ **Échec du Git Pull pour {bot_name}.** Le bot n'a pas été modifié ni redémarré.\n\n"

    await query.edit_message_text(
        final_msg + "\n".join(update_messages),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def deletebot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /deletebot"""
    if not check_admin(update): return

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"delete_{name}")]
                for name in bots.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🗑️ Sélectionnez un bot à supprimer:",
        reply_markup=reply_markup
    )


async def deletebot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour supprimer un bot"""
    query = update.callback_query
    await query.answer()

    bot_name = query.data.replace("delete_", "")

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmer la suppression", callback_data=f"delconfirm_{bot_name}"),
            InlineKeyboardButton("❌ Annuler", callback_data="delcancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⚠️ Êtes-vous sûr de vouloir supprimer **{bot_name}**?\n\n"
        f"Cela supprimera tous les fichiers (dossier **bots/{bot_name}**) et la configuration.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def deletebot_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback pour confirmer la suppression"""
    query = update.callback_query
    await query.answer()

    if query.data == "delcancel":
        await query.edit_message_text("❌ Suppression annulée.")
        return

    bot_name = query.data.replace("delconfirm_", "")
    await query.edit_message_text(f"⏳ Suppression de **{bot_name}** en cours...", parse_mode='Markdown')

    ProcessManager.stop_bot(bot_name)

    bot_dir = BOTS_DIR / bot_name
    if bot_dir.exists():
        try:
            shutil.rmtree(bot_dir)
            logger.info(f"Dossier {bot_name} supprimé.")
        except Exception as e:
            await query.edit_message_text(f"❌ Erreur suppression fichiers: {e}")
            return

    ConfigManager.delete_bot_config(bot_name)

    log_file = LOGS_DIR / f"{bot_name}.log"
    if log_file.exists():
        os.remove(log_file)

    await query.edit_message_text(f"✅ Bot **{bot_name}** supprimé avec succès.", parse_mode='Markdown')


# ============================================================================
# CONVERSATION - NEWBOT (Simplifié)
# ============================================================================

async def newbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation newbot"""
    if not check_admin(update): return ConversationHandler.END

    await update.message.reply_text(
        "🆕 **Création d'un nouveau bot**\n\n"
        "Quel nom voulez-vous donner à ce bot?\n"
        "(Utilisez uniquement des lettres, chiffres et underscores)\n\n"
        "Tapez /cancel pour annuler",
        parse_mode='Markdown'
    )
    return NEWBOT_NAME


async def newbot_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le nom du bot"""
    bot_name = update.message.text.strip().lower()

    if not bot_name.replace('_', '').isalnum():
        await update.message.reply_text(
            "❌ Nom invalide. Utilisez uniquement lettres, chiffres et underscores."
        )
        return NEWBOT_NAME

    if ConfigManager.get_bot_config(bot_name):
        await update.message.reply_text(
            f"❌ Un bot nommé '{bot_name}' existe déjà."
        )
        return NEWBOT_NAME

    context.user_data['newbot_name'] = bot_name

    await update.message.reply_text(
        f"✅ Nom: **{bot_name}**\n\n"
        f"**URL du dépôt GitHub?**\n"
        f"(Ex: `https://github.com/user/my-bot.git`)\n"
        f"Tapez 'skip' si vous voulez ajouter les fichiers manuellement",
        parse_mode='Markdown'
    )
    # Passe directement à NEWBOT_REPO (Token et Prefix sont maintenant facultatifs/manuels)
    return NEWBOT_REPO


async def newbot_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le repo et finalise"""
    repo = update.message.text.strip()

    bot_name = context.user_data.get('newbot_name')

    if not bot_name:
        await update.message.reply_text("❌ Erreur: informations manquantes. Redémarrez avec /newbot.")
        context.user_data.clear()
        return ConversationHandler.END

    bot_config = {
        "token": None, # Non demandé, doit être configuré via /settoken
        "prefix": None, # Non demandé, doit être configuré via /setprefix
        "status": "stopped",
        "created_at": datetime.now().isoformat(),
        "setup_completed": False,
        "restart_count": 0
    }

    if repo.lower() != 'skip':
        bot_config["github_repo"] = repo

    ConfigManager.update_bot_config(bot_name, bot_config)

    context.user_data.clear()

    summary = f"✅ **Bot créé: {bot_name}**\n\n"
    summary += f"\n**Prochaines étapes:**\n"

    if repo.lower() != 'skip':
        summary += "1. Utilisez **/setup** pour cloner et installer\n"
        summary += "2. Utilisez **/settoken** pour ajouter votre Token Discord (OBLIGATOIRE)\n"
        summary += "3. Utilisez **/startbot** pour démarrer"
    else:
        summary += f"1. Ajoutez vos fichiers dans: `bots/{bot_name}`\n"
        summary += "2. Utilisez **/setup** pour installer les dépendances\n"
        summary += "3. Utilisez **/settoken** pour ajouter votre Token Discord (OBLIGATOIRE)\n"
        summary += "4. Utilisez **/startbot** pour démarrer"

    await update.message.reply_text(summary, parse_mode='Markdown')
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule la conversation"""
    context.user_data.clear()
    await update.message.reply_text("❌ Opération annulée.")
    return ConversationHandler.END


# ============================================================================
# CONVERSATION - SETTOKEN (reste inchangé)
# ============================================================================

async def settoken_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation settoken"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"settoken_{name}")]
                for name in bots.keys()]
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="settoken_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔑 Sélectionnez un bot pour changer son token:",
        reply_markup=reply_markup
    )
    return SETTOKEN_SELECT


async def settoken_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du bot"""
    query = update.callback_query
    await query.answer()

    if query.data == "settoken_cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return ConversationHandler.END

    bot_name = query.data.replace("settoken_", "")
    context.user_data['settoken_bot'] = bot_name

    await query.edit_message_text(
        f"🔑 **Changement du token: {bot_name}**\n\n"
        f"Envoyez le nouveau token Discord:\n"
        f"(Le message sera **supprimé** pour votre sécurité)",
        parse_mode='Markdown'
    )
    return SETTOKEN_VALUE


async def settoken_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le nouveau token"""
    token = update.message.text.strip()
    bot_name = context.user_data.get('settoken_bot')

    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Impossible de supprimer le message: {e}")

    if not bot_name:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Erreur: bot non trouvé."
        )
        return ConversationHandler.END

    ConfigManager.update_bot_config(bot_name, {"token": token})

    bot_dir = BOTS_DIR / bot_name
    if bot_dir.exists():
        env_file = bot_dir / ".env"
        try:
            with open(env_file, 'w') as f:
                f.write(f"DISCORD_TOKEN={token}\n")
        except Exception as e:
            logger.error(f"Erreur mise à jour .env pour {bot_name}: {e}")

    context.user_data.clear()

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ Token mis à jour pour **{bot_name}**\n\n"
             f"**Redémarrez** le bot pour appliquer les changements.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ============================================================================
# CONVERSATION - SETPREFIX (reste inchangé)
# ============================================================================

async def setprefix_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation setprefix"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"setprefix_{name}")]
                for name in bots.keys()]
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="setprefix_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ Sélectionnez un bot pour changer son préfixe (Mémo):",
        reply_markup=reply_markup
    )
    return SETPREFIX_SELECT


async def setprefix_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du bot"""
    query = update.callback_query
    await query.answer()

    if query.data == "setprefix_cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return ConversationHandler.END

    bot_name = query.data.replace("setprefix_", "")
    context.user_data['setprefix_bot'] = bot_name

    current_prefix = ConfigManager.get_bot_config(bot_name).get('prefix', 'N/A')

    await query.edit_message_text(
        f"⚙️ **Changement du préfixe: {bot_name}**\n\n"
        f"Préfixe actuel: **{current_prefix}**\n\n"
        f"Envoyez le nouveau préfixe (Mémo Sentinel Host):",
        parse_mode='Markdown'
    )
    return SETPREFIX_VALUE


async def setprefix_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le nouveau préfixe"""
    prefix = update.message.text.strip()
    bot_name = context.user_data.get('setprefix_bot')

    if not bot_name:
        await update.message.reply_text("❌ Erreur: bot non trouvé.")
        return ConversationHandler.END

    ConfigManager.update_bot_config(bot_name, {"prefix": prefix})
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Préfixe mis à jour pour **{bot_name}**: **{prefix}**\n\n"
        f"**Note:** Ceci est un mémo. Le préfixe dans le code de votre bot doit être ajusté manuellement.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ============================================================================
# CONVERSATION - SETREPO (reste inchangé)
# ============================================================================

async def setrepo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation setrepo"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"setrepo_{name}")]
                for name in bots.keys()]
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="setrepo_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📦 Sélectionnez un bot pour changer son dépôt GitHub:",
        reply_markup=reply_markup
    )
    return SETREPO_SELECT


async def setrepo_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du bot"""
    query = update.callback_query
    await query.answer()

    if query.data == "setrepo_cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return ConversationHandler.END

    bot_name = query.data.replace("setrepo_", "")
    context.user_data['setrepo_bot'] = bot_name

    current_repo = ConfigManager.get_bot_config(bot_name).get('github_repo', 'N/A')

    await query.edit_message_text(
        f"📦 **Changement du dépôt: {bot_name}**\n\n"
        f"Repo actuel: `{current_repo}`\n\n"
        f"Envoyez la nouvelle URL GitHub:",
        parse_mode='Markdown'
    )
    return SETREPO_VALUE


async def setrepo_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère la nouvelle URL"""
    repo = update.message.text.strip()
    bot_name = context.user_data.get('setrepo_bot')

    if not bot_name:
        await update.message.reply_text("❌ Erreur: bot non trouvé.")
        return ConversationHandler.END

    ConfigManager.update_bot_config(bot_name, {"github_repo": repo, "setup_completed": False})
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Dépôt mis à jour pour **{bot_name}**\n\n"
        f"Utilisez **/setup** pour cloner le nouveau dépôt et mettre à jour les dépendances.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ============================================================================
# CONVERSATION - EXECBOT (reste inchangé)
# ============================================================================

async def execbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation execbot"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"execbot_{name}")]
                for name in bots.keys()]
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="execbot_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚡ Sélectionnez un bot pour exécuter une commande (dans son dossier):",
        reply_markup=reply_markup
    )
    return EXECBOT_SELECT


async def execbot_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du bot"""
    query = update.callback_query
    await query.answer()

    if query.data == "execbot_cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return ConversationHandler.END

    bot_name = query.data.replace("execbot_", "")
    context.user_data['execbot_bot'] = bot_name

    await query.edit_message_text(
        f"⚡ **Exécution de commande: {bot_name}**\n\n"
        f"Entrez la commande à exécuter (Ex: `ls`, `git pull`, `cat main.py`):\n"
        f"**Attention:** Exécutée dans le shell du VPS!",
        parse_mode='Markdown'
    )
    return EXECBOT_COMMAND


async def execbot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exécute la commande"""
    command = update.message.text.strip()
    bot_name = context.user_data.get('execbot_bot')

    if not bot_name:
        await update.message.reply_text("❌ Erreur: bot non trouvé.")
        return ConversationHandler.END

    await update.message.reply_text(f"⏳ Exécution de `{command}` dans **{bot_name}**...", parse_mode='Markdown')

    bot_dir = BOTS_DIR / bot_name
    if not bot_dir.exists():
        await update.message.reply_text(f"❌ Dossier de {bot_name} introuvable.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        result = subprocess.run(
            command,
            cwd=str(bot_dir),
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout.strip() if result.stdout else result.stderr.strip()
        if not output:
            output = "✅ Commande exécutée (pas de sortie)"

        if len(output) > 3500:
            output = output[:3500] + "\n...(tronqué)"

        await update.message.reply_text(
            f"⚡ **Résultat:** (Code: {result.returncode})\n\n```\n{output}\n```",
            parse_mode='Markdown'
        )

    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Timeout: commande trop longue à exécuter.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================================
# CONVERSATION - PIPINSTALL (reste inchangé)
# ============================================================================

async def pipinstall_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début de la conversation pipinstall"""
    if not check_admin(update): return ConversationHandler.END

    config = ConfigManager.load_config()
    bots = config.get("bots", {})

    if not bots:
        await update.message.reply_text("ℹ️ Aucun bot configuré.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(name, callback_data=f"pipinstall_{name}")]
                for name in bots.keys()]
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="pipinstall_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📦 Sélectionnez un bot pour installer un package Python (dans son venv):",
        reply_markup=reply_markup
    )
    return PIPINSTALL_SELECT


async def pipinstall_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du bot"""
    query = update.callback_query
    await query.answer()

    if query.data == "pipinstall_cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return ConversationHandler.END

    bot_name = query.data.replace("pipinstall_", "")
    context.user_data['pipinstall_bot'] = bot_name

    await query.edit_message_text(
        f"📦 **Installation de package: {bot_name}**\n\n"
        f"Entrez le nom du package à installer:\n"
        f"(Ex: `discord.py`, `requests`, `pandas` etc.)",
        parse_mode='Markdown'
    )
    return PIPINSTALL_PACKAGE


async def pipinstall_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Installe le package"""
    package = update.message.text.strip()
    bot_name = context.user_data.get('pipinstall_bot')

    if not bot_name:
        await update.message.reply_text("❌ Erreur: bot non trouvé.")
        return ConversationHandler.END

    bot_dir = BOTS_DIR / bot_name
    venv_dir = bot_dir / "venv"

    if not venv_dir.exists():
        await update.message.reply_text(
            f"❌ Environnement virtuel introuvable pour **{bot_name}**.\n"
            f"Exécutez **/setup** d'abord.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END

    pip_path = BotSetup._get_venv_pip_path(bot_name)

    await update.message.reply_text(f"⏳ Installation de **{package}** en cours pour **{bot_name}**...", parse_mode='Markdown')

    try:
        result = subprocess.run(
            [str(pip_path), "install", package],
            cwd=str(bot_dir),
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            await update.message.reply_text(
                f"✅ Package **{package}** installé avec succès pour **{bot_name}**.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Erreur lors de l'installation de **{package}**:\n\n```\n{result.stderr[:500]}\n```",
                parse_mode='Markdown'
            )

    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Timeout: installation trop longue.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================================
# MAIN - INITIALISATION ET DÉMARRAGE
# ============================================================================

async def post_init(application: Application):
    """Actions après l'initialisation"""
    logger.info("🛡️ Sentinel Host démarré")

    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="🛡️ **Sentinel Host** démarré et opérationnel!\n\n"
                 "Utilisez /start pour voir les commandes disponibles.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur envoi notification (Vérifiez ADMIN_CHAT_ID et TELEGRAM_BOT_TOKEN): {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire d'erreurs global"""
    logger.error(f"❌ Erreur: {context.error}", exc_info=context.error)

    try:
        error_message = f"❌ Une erreur est survenue: `{context.error}`. Veuillez réessayer."

        if update and update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(error_message, parse_mode='Markdown')
        elif update and update.effective_message:
            await update.effective_message.reply_text(error_message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Erreur lors de la notification de l'erreur à l'utilisateur: {e}")


def main():
    """Point d'entrée principal"""

    logger.info("=" * 60)
    logger.info("🛡️  SENTINEL HOST - Manager de Bots Discord")
    logger.info("=" * 60)
    logger.info(f"📁 Dossier racine: {BASE_DIR}")
    logger.info(f"🤖 Dossier bots: {BOTS_DIR}")
    logger.info(f"📋 Dossier logs: {LOGS_DIR}")
    logger.info(f"💾 Dossier backups: {BACKUPS_DIR}")
    logger.info("=" * 60)

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ========================================================================
    # HANDLERS - Commandes simples & Sécurité
    # ========================================================================

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CallbackQueryHandler(health_callback, pattern="^health_"))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CallbackQueryHandler(logs_callback, pattern="^logs_"))

    application.add_handler(CommandHandler("startbot", startbot_command))
    application.add_handler(CallbackQueryHandler(startbot_callback, pattern="^start_"))
    application.add_handler(CommandHandler("stopbot", stopbot_command))
    application.add_handler(CallbackQueryHandler(stopbot_callback, pattern="^stop_"))
    application.add_handler(CommandHandler("restartbot", restartbot_command))
    application.add_handler(CallbackQueryHandler(restartbot_callback, pattern="^restart_"))

    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CallbackQueryHandler(setup_callback, pattern="^setup_"))
    application.add_handler(CommandHandler("deletebot", deletebot_command))
    application.add_handler(CallbackQueryHandler(deletebot_callback, pattern="^delete_"))
    application.add_handler(CallbackQueryHandler(deletebot_confirm_callback, pattern="^delconfirm_|^delcancel$"))

    # ========================================================================
    # NOUVEAU HANDLER: /updatebot
    # ========================================================================
    updatebot_conv = ConversationHandler(
        entry_points=[CommandHandler("updatebot", updatebot_start)],
        states={
            UPDATEBOT_SELECT: [CallbackQueryHandler(updatebot_callback, pattern="^update_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(updatebot_conv)

    # ========================================================================
    # CONVERSATION HANDLERS
    # ========================================================================

    # /newbot (Flux NEWBOT_TOKEN et NEWBOT_PREFIX supprimés)
    newbot_conv = ConversationHandler(
        entry_points=[CommandHandler("newbot", newbot_start)],
        states={
            NEWBOT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, newbot_name)],
            NEWBOT_REPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, newbot_repo)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(newbot_conv)

    # /settoken
    settoken_conv = ConversationHandler(
        entry_points=[CommandHandler("settoken", settoken_start)],
        states={
            SETTOKEN_SELECT: [CallbackQueryHandler(settoken_select, pattern="^settoken_[^cancel]$|^settoken_cancel$")],
            SETTOKEN_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settoken_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(settoken_conv)

    # /setprefix
    setprefix_conv = ConversationHandler(
        entry_points=[CommandHandler("setprefix", setprefix_start)],
        states={
            SETPREFIX_SELECT: [CallbackQueryHandler(setprefix_select, pattern="^setprefix_[^cancel]$|^setprefix_cancel$")],
            SETPREFIX_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setprefix_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(setprefix_conv)

    # /setrepo
    setrepo_conv = ConversationHandler(
        entry_points=[CommandHandler("setrepo", setrepo_start)],
        states={
            SETREPO_SELECT: [CallbackQueryHandler(setrepo_select, pattern="^setrepo_[^cancel]$|^setrepo_cancel$")],
            SETREPO_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setrepo_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(setrepo_conv)

    # /execbot
    execbot_conv = ConversationHandler(
        entry_points=[CommandHandler("execbot", execbot_start)],
        states={
            EXECBOT_SELECT: [CallbackQueryHandler(execbot_select, pattern="^execbot_[^cancel]$|^execbot_cancel$")],
            EXECBOT_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, execbot_command)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(execbot_conv)

    # /pipinstall
    pipinstall_conv = ConversationHandler(
        entry_points=[CommandHandler("pipinstall", pipinstall_start)],
        states={
            PIPINSTALL_SELECT: [CallbackQueryHandler(pipinstall_select, pattern="^pipinstall_[^cancel]$|^pipinstall_cancel$")],
            PIPINSTALL_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pipinstall_package)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )
    application.add_handler(pipinstall_conv)

    # ========================================================================
    # ERROR HANDLER
    # ========================================================================

    application.add_error_handler(error_handler)

    # ========================================================================
    # JOB QUEUE - Monitoring
    # ========================================================================

    job_queue = application.job_queue

    if job_queue:
        job_queue.run_repeating(
            BotMonitor.monitor_loop,
            interval=CHECK_INTERVAL,
            first=10
        )
        logger.info("✅ Monitoring automatique JobQueue activé.")
    else:
        logger.warning("❌ JobQueue non disponible. Le monitoring automatique est désactivé.")
        logger.warning("Pour l'activer, installez la dépendance : pip install \"python-telegram-bot[job-queue]\"")


    # ========================================================================
    # DÉMARRAGE
    # ========================================================================

    logger.info("🚀 Démarrage du bot Telegram...")
    logger.info(f"👤 Admin Chat ID: {ADMIN_CHAT_ID}")
    logger.info(f"🔄 Intervalle de monitoring: {CHECK_INTERVAL}s")
    logger.info(f"💾 Limite mémoire par bot: {MAX_MEMORY_MB}MB")
    logger.info("=" * 60)

    # Démarrer le bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du Sentinel Host...")
    except Exception as e:
        logger.critical(f"❌ Erreur fatale: {e}", exc_info=True)
        sys.exit(1)
# 🛡️ Sentinel Host

> A powerful Discord bot manager controlled entirely through Telegram

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)](https://github.com/Rayco-maker/sentinel-host)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Sentinel Host** is a robust, cross-platform Python system for centralized management and monitoring of multiple Discord bots from a single VPS or local machine. Control everything remotely through an intuitive Telegram bot interface.

---

## ✨ Features

- **🤖 Telegram Control Interface** - Manage all bots remotely through Telegram commands
- **🔄 One-Command Updates** - Auto-update bots with Git pull, dependency reinstall, and restart
- **📊 Intelligent Monitoring** - Automatic crash detection, restart management, and memory alerts
- **🔒 Isolated Environments** - Each bot runs in its own Python virtual environment
- **🌐 Cross-Platform** - Works seamlessly on Windows and Linux (VPS ready)
- **📝 Comprehensive Logging** - Track every action and error with dedicated log files

---

## 📋 Table of Contents

- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Usage](#-usage)
- [Commands Reference](#-commands-reference)
- [Troubleshooting](#-troubleshooting)

---

## 🔧 Prerequisites

Before installing Sentinel Host, ensure you have:

| Requirement | Version | Notes |
|------------|---------|-------|
| **Python** | 3.11 or 3.12 | Recommended for stability |
| **Git** | Latest | Required for bot updates |
| **Telegram Bot Token** | - | Obtain from [@BotFather](https://t.me/botfather) |
| **Telegram Chat ID** | - | Your numerical user ID |

### Getting Your Telegram Credentials

1. **Bot Token**: Message [@BotFather](https://t.me/botfather) on Telegram
   - Send `/newbot`
   - Follow prompts to create your bot
   - Save the token provided

2. **Chat ID**: Message [@userinfobot](https://t.me/userinfobot)
   - Your numerical ID will be displayed
   - Save this number (e.g., `123456789`)

---

## 📦 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/Rayco-maker/sentinel-host.git
cd sentinel-host
```

### Step 2: Create Virtual Environment

**Windows:**
```bash
py -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
pip install "python-telegram-bot[job-queue]"
```

> **Note**: The `job-queue` module is mandatory for monitoring features.

---

## ⚙️ Configuration

### Edit Configuration File

Open `bot_manager.py` and update the following variables (lines 37-39):

```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # From BotFather
ADMIN_CHAT_ID = YOUR_NUMERICAL_CHAT_ID          # Your Telegram user ID
GITHUB_PAT = ""                                  # Optional: For private repos
```

### Environment Variables (Alternative)

You can also use environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
export ADMIN_CHAT_ID="your_chat_id_here"
```

---

## 🚀 Deployment

### Option A: Local/Development

Run directly while the virtual environment is active:

```bash
python bot_manager.py
```

### Option B: Production (Linux VPS with systemd)

For 24/7 operation on a Linux server, use systemd:

#### 1. Create Service File

```bash
sudo nano /etc/systemd/system/sentinelhost.service
```

#### 2. Configure Service

Replace `your_linux_username` with your actual username:

```ini
[Unit]
Description=Sentinel Host Discord Bot Manager
After=network.target

[Service]
User=your_linux_username
WorkingDirectory=/home/your_linux_username/sentinel-host
ExecStart=/home/your_linux_username/sentinel-host/venv/bin/python bot_manager.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### 3. Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable sentinelhost.service
sudo systemctl start sentinelhost.service
```

#### 4. Verify Status

```bash
sudo systemctl status sentinelhost.service
```

---

## 📱 Usage

### Initial Bot Setup Workflow

Follow these steps to add and deploy a new Discord bot:

| Step | Command | Description |
|------|---------|-------------|
| **1. Register** | `/newbot` | Initiate bot registration with name and GitHub URL |
| **2. Setup** | `/setup [bot_name]` | Clone repository and install dependencies |
| **3. Configure** | `/settoken [bot_name]` | Store Discord token (creates `.env` file) |
| **4. Launch** | `/startbot [bot_name]` | Start the bot process |

**Example:**
```
/newbot
→ Bot Name: MyDiscordBot
→ GitHub URL: https://github.com/username/bot-repo

/setup MyDiscordBot
/settoken MyDiscordBot
→ Token: YOUR_DISCORD_BOT_TOKEN

/startbot MyDiscordBot
```

---

## 🎮 Commands Reference

### 📦 Core Management

| Command | Description | Example |
|---------|-------------|---------|
| `/newbot` | Register a new bot | `/newbot` |
| `/setup [name]` | Clone repo and setup environment | `/setup MyBot` |
| `/settoken [name]` | Configure Discord token | `/settoken MyBot` |
| `/startbot [name]` | Start a bot | `/startbot MyBot` |
| `/stopbot [name]` | Stop a running bot | `/stopbot MyBot` |
| `/restartbot [name]` | Restart a bot | `/restartbot MyBot` |
| `/removebot [name]` | Delete bot and all data | `/removebot MyBot` |

### 🔄 Maintenance

| Command | Description | Details |
|---------|-------------|---------|
| `/updatebot [name]` | Update bot from Git | Pulls latest code, reinstalls dependencies, restarts |
| `/setrepo [name]` | Change GitHub repository | Updates the linked repo URL |
| `/setprefix [name]` | Set display prefix | Quick reference label for `/health` |

### 📊 Monitoring

| Command | Description | Output |
|---------|-------------|--------|
| `/status` | Quick status overview | Shows 🟢 running / 🔴 stopped status |
| `/health` | Detailed metrics | CPU, RAM, PID, uptime for all bots |
| `/logs [name]` | View recent logs | Last 50 lines from bot's log file |

### 🔧 Advanced

| Command | Description | ⚠️ Warning |
|---------|-------------|-----------|
| `/execbot [name] [cmd]` | Execute shell command | Use with extreme caution - runs in bot directory |

**Example:**
```bash
/execbot MyBot ls -la
```

---

## 🛠️ Troubleshooting

### Common Issues

#### Bot Won't Start
```bash
# Check if virtual environment exists
ls bots/[bot_name]/venv

# Manually reinstall dependencies
cd bots/[bot_name]
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

#### Update Failed
- Ensure Git is installed and accessible
- Check GitHub repository permissions
- Verify network connectivity

#### Permission Denied (Linux)
```bash
# Fix ownership
sudo chown -R $USER:$USER ~/sentinel-host

# Fix permissions
chmod +x bots/*/venv/bin/python
```

### Logs Location

- **Sentinel Host Logs**: `sentinel_host.log`
- **Bot Logs**: `bots/[bot_name]/bot.log`

### Systemd Service Logs

```bash
# View recent logs
sudo journalctl -u sentinelhost.service -n 50

# Follow live logs
sudo journalctl -u sentinelhost.service -f
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- Inspired by the need for centralized bot management

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Rayco-maker/sentinel-host/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Rayco-maker/sentinel-host/discussions)

---

<div align="center">

**Made with ❤️ for the Discord bot community**

[⬆ Back to Top](#️-sentinel-host)

</div>

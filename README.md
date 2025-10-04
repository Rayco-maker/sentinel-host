Sentinel Host is a powerful, cross-platform Python system designed to manage and monitor multiple Discord bots from a single Virtual Private Server (VPS) or local machine. All control—start, stop, updates, and health checks—is performed through a Telegram Bot interface.

🚀 Key Features
Centralized Control: Manage all bots from Telegram (mobile or desktop).

Intelligent Monitoring: Automatic detection and restart of crashed bots.

Cross-Platform: Full compatibility with Windows and Linux (essential for VPS).

Easy Deployment: Guided setup for cloning GitHub repositories, creating isolated Python Virtual Environments (venv), and installing dependencies.

Maintenance Tools: Commands for running shell commands (/execbot), installing new packages (/pipinstall), and performing full code updates (/updatebot).

⚙️ Installation and Setup
Prerequisites
Python 3.10+ installed on your host machine (Windows or VPS).

Git installed and accessible via the command line.

Telegram Bot Token: Obtained from BotFather on Telegram.

Telegram Admin Chat ID: Your personal Telegram user ID (numerical).

Step 1: Clone the Project and Create Venv
Open your terminal (or PyCharm Terminal) and execute the following:

Bash

# Clone the repository (replace [REPO_URL] with the actual URL)
git clone [REPO_URL] sentinel-host
cd sentinel-host

# Create a Python Virtual Environment
python -m venv venv

# Activate the Virtual Environment
# Linux/macOS:
# source venv/bin/activate
# Windows (CMD):
venv\Scripts\activate
Step 2: Install Dependencies
Sentinel Host requires its core dependencies, including the optional job-queue module for recurring monitoring tasks.

With the venv active, run:

Bash

pip install -r requirements.txt
pip install "python-telegram-bot[job-queue]"
Note: If you experience issues, ensure your requirements.txt includes the correct versions (python-telegram-bot, psutil, etc.).

Step 3: Configuration (Edit bot_manager.py)
Open the bot_manager.py file and edit the configuration variables at the top of the script with your tokens and IDs:

Python

# Tokens et IDs (À REMPLACER PAR VOS VRAIES VALEURS)
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" # <-- REPLACE THIS
ADMIN_CHAT_ID = YOUR_NUMERICAL_CHAT_ID       # <-- REPLACE THIS
GITHUB_PAT = "ghp_..." # Optional, for private repositories
Step 4: Run Sentinel Host
Run the main script:

Bash

python bot_manager.py
Sentinel Host should send a welcome message to your configured ADMIN_CHAT_ID on Telegram.

💻 Deployment on a VPS (Linux)
For reliable 24/7 hosting, deploying on a Linux VPS using a persistent service manager like screen or systemd is recommended.

Option A: Using screen (Simple Persistent Session)
Complete Steps 1-3 from the general setup above.

Install screen if needed: sudo apt update && sudo apt install screen -y

Start a new screen session (this keeps the program running even if you disconnect):

Bash

screen -S sentinel_session
Activate the venv and run the bot inside the screen session:

Bash

source venv/bin/activate
python bot_manager.py
Detach from the screen session (the process keeps running):

Bash

# Press: Ctrl + A + D
To reattach later: screen -r sentinel_session

Option B: Using systemd (Production Recommended)
Complete Steps 1-3 from the general setup.

Create a service file: sudo nano /etc/systemd/system/sentinelhost.service

Paste the following content (replace paths and user):

Ini, TOML

[Unit]
Description=Sentinel Host Discord Bot Manager
After=network.target

[Service]
User=your_linux_username       # <-- REPLACE THIS
WorkingDirectory=/home/your_linux_username/sentinel-host # <-- REPLACE THIS
ExecStart=/home/your_linux_username/sentinel-host/venv/bin/python bot_manager.py # <-- REPLACE THIS
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
Save and exit (Ctrl + X, then Y, then Enter).

Enable and start the service:

Bash

sudo systemctl daemon-reload
sudo systemctl enable sentinelhost.service
sudo systemctl start sentinelhost.service
Check the status: sudo systemctl status sentinelhost.service

📋 Bot Management Commands (via Telegram)
Once Sentinel Host is running, interact with it using your Telegram Bot:

Category	Command	Description
Provisioning	/newbot	Starts the conversation to register a new bot.
/setup	Clones the GitHub repository, creates the venv, and installs dependencies.
/deletebot	Removes the bot's files and configuration completely.
Control	/startbot	Starts a stopped bot process.
/stopbot	Gracefully stops a running bot process.
/restartbot	Stops and immediately restarts a bot.
Maintenance	/updatebot	Performs Git Pull, re-runs Setup (updates venv/deps), and restarts the bot.
/settoken	Updates the Discord token (updates config and .env file).
/setrepo	Updates the GitHub repository URL.
Monitoring	/status	Shows the running status (🟢/🔴) of all managed bots.
/health	Shows detailed stats (CPU, RAM, PID, Uptime) for a selected bot.
/logs	Displays the last 50 lines of the bot's log file.

Exporter vers Sheets
🆕 Workflow Example: Adding a Bot
Telegram: Send /newbot

Bot: Enter the bot's name (e.g., musicbot).

Bot: Enter the bot's GitHub repository URL (e.g., https://github.com/user/musicbot.git).

Telegram: Send /setup musicbot to provision the environment.

Telegram: Send /settoken musicbot and paste your Discord bot token.

Telegram: Send /startbot musicbot to launch your bot.

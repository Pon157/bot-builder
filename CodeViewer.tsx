
import React from 'react';
import { BotConfig } from '../types';
import { generatePythonCode } from '../services/pythonGenerator';

interface CodeViewerProps {
  bot: BotConfig;
  onBack: () => void;
}

const CodeViewer: React.FC<CodeViewerProps> = ({ bot, onBack }) => {
  const code = generatePythonCode(bot);
  const serviceName = `bot_${bot.id.slice(0, 5)}`;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert("Copied to clipboard!");
  };

  const systemdConfig = `[Unit]
Description=Telegram Bot ${bot.name}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/${serviceName}
ExecStart=/root/${serviceName}/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target`;

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in slide-in-from-right-4 duration-500 pb-20">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-4">
            <button onClick={onBack} className="p-2 hover:bg-zinc-800 rounded-lg transition-colors text-zinc-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h1 className="text-2xl font-bold">Ubuntu Server Deployment</h1>
        </div>
        <div className="flex gap-2">
            <button onClick={() => copyToClipboard(code)} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2">
                Copy Python Code
            </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
            <div className="bg-[#121212] rounded-2xl border border-zinc-800 overflow-hidden">
                <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 flex justify-between items-center">
                    <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">1. Ubuntu Terminal Setup</span>
                </div>
                <div className="p-4 bg-black">
                    <pre className="text-[11px] text-green-400 font-mono leading-relaxed overflow-x-auto">
{`# Update system
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv -y

# Create project folder
mkdir ${serviceName} && cd ${serviceName}

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install professional requirements
pip install aiogram aiosqlite

# Create the bot file
nano main.py
# (Paste the Python code here and save: Ctrl+O, Enter, Ctrl+X)`}
                    </pre>
                </div>
            </div>

            <div className="bg-[#121212] rounded-2xl border border-zinc-800 overflow-hidden">
                <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 flex justify-between items-center">
                    <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">2. Auto-Restart Service (systemd)</span>
                    <button onClick={() => copyToClipboard(systemdConfig)} className="text-[10px] text-blue-400 font-bold uppercase">Copy Config</button>
                </div>
                <div className="p-4 bg-black">
                    <pre className="text-[11px] text-zinc-400 font-mono leading-relaxed overflow-x-auto">
{`# Create service file
sudo nano /etc/systemd/system/${serviceName}.service

# (Paste the config below into nano)

# Start and enable bot
sudo systemctl daemon-reload
sudo systemctl start ${serviceName}
sudo systemctl enable ${serviceName}

# Check logs
sudo journalctl -u ${serviceName} -f`}
                    </pre>
                </div>
            </div>
        </div>

        <div className="space-y-6">
            <div className="bg-zinc-900/50 rounded-2xl border border-zinc-800 p-6">
                <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                    <svg className="w-4 h-4 text-blue-500" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a8 8 0 100 16 8 8 0 000-16zm3.707 6.707l-4 4a1 1 0 01-1.414 0l-2-2a1 1 0 111.414-1.414L9 10.586l3.293-3.293a1 1 0 011.414 1.414z"/></svg>
                    Production Features Enabled
                </h3>
                <ul className="text-xs text-zinc-400 space-y-3">
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">✓</span>
                        <div>
                            <p className="text-zinc-200 font-semibold">Async SQLite Database</p>
                            <p>Automatically handles user registration and message history on disk.</p>
                        </div>
                    </li>
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">✓</span>
                        <div>
                            <p className="text-zinc-200 font-semibold">Professional Broadcast Engine</p>
                            <p>Command <code>/broadcast</code> is restricted to Admin and includes anti-flood protection.</p>
                        </div>
                    </li>
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">✓</span>
                        <div>
                            <p className="text-zinc-200 font-semibold">Auto-Healing Service</p>
                            <p>If the bot crashes or the server reboots, systemd will restart it in 5 seconds.</p>
                        </div>
                    </li>
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">✓</span>
                        <div>
                            <p className="text-zinc-200 font-semibold">Admin Relay System</p>
                            <p>Forwarding messages to Admin with support for direct replies in Telegram.</p>
                        </div>
                    </li>
                </ul>
            </div>

            <div className="bg-blue-600/10 border border-blue-500/20 rounded-2xl p-6">
                <p className="text-xs text-blue-400 font-bold mb-2">Systemd Config for ${serviceName}.service</p>
                <pre className="text-[10px] text-blue-200 font-mono overflow-x-auto">
                    {systemdConfig}
                </pre>
            </div>
        </div>
      </div>
    </div>
  );
};

export default CodeViewer;

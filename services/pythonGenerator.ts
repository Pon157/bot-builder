
import { BotConfig } from '../types';

export const generatePythonCode = (config: BotConfig): string => {
  const configJson = JSON.stringify(config, null, 2);

  return `#!/usr/bin/env python3
import os
import json
import subprocess
import sys

# Сгенерировано BotEngine Pro
CONFIG = ${configJson}

# Создаем временный файл конфигурации
config_path = os.path.join(os.getcwd(), f"config_{CONFIG['id']}.json")
with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(CONFIG, f, ensure_ascii=False)

# Запуск ядра bot_core.py
try:
    print(f"🚀 Запуск инстанса: {CONFIG['name']}")
    subprocess.run([sys.executable, "bot_core.py", config_path])
except KeyboardInterrupt:
    pass
finally:
    if os.path.exists(config_path):
        os.remove(config_path)
`;
};

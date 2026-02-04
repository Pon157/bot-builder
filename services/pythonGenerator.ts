
import { BotConfig } from '../types';

export const generatePythonCode = (config: BotConfig): string => {
  const configJson = JSON.stringify(config, null, 2);

  return `#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import subprocess
import sys
import time

# Конфигурация, сгенерированная BotEngine Pro
CONFIG = ${configJson}

def main():
    bot_id = CONFIG.get('id', 'unknown')
    print(f"[*] Инициализация инстанса {bot_id}...")
    
    # Путь к временному конфигу
    config_path = os.path.join(os.getcwd(), f"config_{bot_id}.json")
    
    try:
        # Записываем конфиг
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
            
        print(f"[*] Конфигурация сохранена в {config_path}")
        print(f"[*] Запуск основного ядра bot_core.py...")
        
        # Запускаем ядро. Оно должно находиться в той же директории или в PYTHONPATH
        process = subprocess.run(
            [sys.executable, "bot_core.py", config_path],
            env=os.environ.copy(),
            check=False
        )
        
        if process.returncode != 0:
            print(f"[!] Ядро завершилось с ошибкой {process.returncode}")
            
    except Exception as e:
        print(f"[!] Критическая ошибка при запуске: {e}")
    finally:
        # Очистка
        if os.path.exists(config_path):
            try:
                os.remove(config_path)
                print(f"[*] Временный файл {config_path} удален.")
            except:
                pass

if __name__ == "__main__":
    main()
`;
};

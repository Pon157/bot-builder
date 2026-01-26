
import { BotConfig } from '../types';

// Используйте адрес вашего сервера. Если фронтенд и бэкенд на одном хосте, можно оставить относительный путь или указать порт.
const API_BASE = 'http://localhost:8000/api';

export const api = {
  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetch(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      return await response.json();
    } catch (e) {
      console.error("API Error (getBots):", e);
      return [];
    }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetch(`${API_BASE}/bots/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bot)
      });
    } catch (e) {
      console.error("API Error (saveBot):", e);
    }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetch(`${API_BASE}/bots/${botId}`, {
        method: 'DELETE'
      });
    } catch (e) {
      console.error("API Error (deleteBot):", e);
    }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/bots/start/${bot.id}`, {
        method: 'POST'
      });
      return response.ok;
    } catch (e) {
      console.error("API Error (startBot):", e);
      return false;
    }
  },

  stopBotOnServer: async (botId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/bots/stop/${botId}`, {
        method: 'POST'
      });
      return response.ok;
    } catch (e) {
      console.error("API Error (stopBot):", e);
      return false;
    }
  }
};

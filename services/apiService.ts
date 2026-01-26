
import { BotConfig, User } from '../types';

// Динамически определяем адрес API. Если фронт открыт по IP 72.56.67.123, 
// то запросы будут уходить на http://72.56.67.123:8000
const getApiBase = () => {
  const host = window.location.hostname;
  return `http://${host}:8000/api`;
};

const API_BASE = getApiBase();

export const api = {
  // Auth
  login: async (email: string, password: string): Promise<User | null> => {
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Auth Error (login):", e);
      return null;
    }
  },

  register: async (userData: any): Promise<User | null> => {
    try {
      const response = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(userData)
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Auth Error (register):", e);
      return null;
    }
  },

  // Bots
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

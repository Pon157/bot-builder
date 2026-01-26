
import { BotConfig, User } from '../types';

const getApiBase = () => {
  const host = window.location.hostname;
  const protocol = window.location.protocol;
  // Если вы заходите через IP, используем его. 
  // ВАЖНО: Убедитесь, что порт 8000 открыт в фаерволе сервера!
  return `${protocol}//${host}:8000/api`;
};

const API_BASE = getApiBase();

// Универсальный fetch с таймаутом
const fetchWithTimeout = async (url: string, options: any = {}, timeout = 10000) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
};

export const api = {
  login: async (email: string, password: string): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Auth Error (login):", e);
      throw e; // Пробрасываем ошибку для обработки в UI
    }
  },

  register: async (userData: any): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(userData)
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Registration failed');
      }
      return await response.json();
    } catch (e) {
      console.error("Auth Error (register):", e);
      throw e;
    }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      return await response.json();
    } catch (e) {
      console.error("API Error (getBots):", e);
      return [];
    }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/save`, {
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
      await fetchWithTimeout(`${API_BASE}/bots/${botId}`, {
        method: 'DELETE'
      });
    } catch (e) {
      console.error("API Error (deleteBot):", e);
    }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, {
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
      const response = await fetchWithTimeout(`${API_BASE}/bots/stop/${botId}`, {
        method: 'POST'
      });
      return response.ok;
    } catch (e) {
      console.error("API Error (stopBot):", e);
      return false;
    }
  }
};

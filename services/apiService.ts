
import { BotConfig, User } from '../types';

const getApiBase = () => {
  const host = window.location.hostname;
  const protocol = window.location.protocol;
  // Если порт 8000 недоступен, проверьте firewall на сервере!
  return `${protocol}//${host}:8000/api`;
};

const API_BASE = getApiBase();

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 8000) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
};

export const api = {
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/ping`, { method: 'GET' }, 3000);
      return res.ok;
    } catch (e) {
      return false;
    }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) return null;
    return await response.json();
  },

  register: async (userData: any): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userData)
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Registration failed');
    }
    return await response.json();
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
    return response.ok ? await response.json() : [];
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    await fetchWithTimeout(`${API_BASE}/bots/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bot)
    });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean> => {
    const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
    return res.ok;
  },

  stopBotOnServer: async (botId: string): Promise<boolean> => {
    const res = await fetchWithTimeout(`${API_BASE}/bots/stop/${botId}`, { method: 'POST' });
    return res.ok;
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${API_BASE}/bots/${botId}`, { method: 'DELETE' });
  }
};

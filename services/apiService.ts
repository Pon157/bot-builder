
import { BotConfig, User } from '../types';

const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000/api`;

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 10000) => {
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
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    return response.ok ? await response.json() : null;
  },

  register: async (userData: any): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userData)
    });
    return response.ok ? await response.json() : null;
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

  // Fix: Added missing deleteBot method used in App.tsx
  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${API_BASE}/bots/delete/${userId}/${botId}`, {
      method: 'DELETE'
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

  sendBroadcast: async (botIds: string[], message: string): Promise<any> => {
    const res = await fetchWithTimeout(`${API_BASE}/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ botIds, message })
    });
    return res.ok ? await res.json() : null;
  }
};

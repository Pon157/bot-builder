
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
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      }, 20000);
      if (!response.ok) return null;
      return await response.json();
    } catch (e) { return null; }
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/auth/request-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      }, 20000);
      if (res.ok) return true;
      const data = await res.json();
      return data.detail || "Error";
    } catch (e) { return false; }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/auth/verify-and-register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      }, 20000);
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      }, 20000);
      if (res.ok) return true;
      const data = await res.json();
      return data.detail || "Error";
    } catch (e) { return false; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      }, 20000);
      return res.ok;
    } catch (e) { return false; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bot)
      });
    } catch (e) { console.error("Failed to save bot"); }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/delete/${botId}`, {
        method: 'DELETE'
      });
    } catch (e) { console.error("Failed to delete bot"); }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
      if (res.ok) return true;
      const errorData = await res.json();
      return errorData.detail || "Error";
    } catch (e) { return "Network Error"; }
  },

  stopBotOnServer: async (botId: string): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/stop/${botId}`, { method: 'POST' });
      return res.ok;
    } catch (e) { return false; }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/broadcast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ botIds, message })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ botId, key })
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  }
};

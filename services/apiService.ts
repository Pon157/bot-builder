
import { BotConfig, User } from '../types';

// Используем текущий хост и порт 8000 для API
const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000/api`;

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 12000) => {
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
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) { return null; }
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/request-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || "Ошибка отправки кода";
    } catch (e) { 
      console.error("Verification error:", e);
      return "Нет связи с API сервером"; 
    }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/verify-and-register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || "Ошибка";
    } catch (e) { return "Ошибка сервера"; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) { return false; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      return await response.json();
    } catch (e) { return []; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ botId, key })
      });
      return await response.json();
    } catch (e: any) { 
      return { status: 'error', detail: e.message }; 
    }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bot)
      });
    } catch (e) { console.error("Failed to save bot", e); }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/delete/${botId}`, {
        method: 'DELETE'
      });
    } catch (e) { console.error("Failed to delete bot", e); }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
      if (res.ok) return true;
      const errorData = await res.json();
      return errorData.detail || "Error starting bot";
    } catch (e) { return "Ошибка сети"; }
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
      if (!res.ok) return null;
      return await res.json();
    } catch (e) { return null; }
  }
};

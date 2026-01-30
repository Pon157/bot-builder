
import { BotConfig, User } from '../types';

// Используем относительный путь, чтобы работать через прокси Vite/Nginx
const API_BASE = '/api';

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 20000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timer);
    return response;
  } catch (error) {
    clearTimeout(timer);
    throw error;
  }
};

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    return data.detail || data.message || "Произошла ошибка на стороне сервера";
  } catch (e) {
    return `Ошибка сервера (${response.status})`;
  }
};

export const api = {
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
      const msg = await getErrorMessage(response);
      throw new Error(msg);
    }
    return await response.json();
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/request-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      return await getErrorMessage(response);
    } catch (e: any) { 
      return e.name === 'AbortError' ? "Сервер не ответил вовремя" : "Ошибка сетевого соединения"; 
    }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/verify-and-register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      const msg = await getErrorMessage(response);
      throw new Error(msg);
    }
    return await response.json();
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    if (response.ok) return true;
    return await getErrorMessage(response);
  },

  resetPassword: async (data: any): Promise<boolean> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      const msg = await getErrorMessage(response);
      throw new Error(msg);
    }
    return response.ok;
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      return await response.json();
    } catch (e) { return []; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    const response = await fetchWithTimeout(`${API_BASE}/license/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ botId, key })
    });
    return await response.json();
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    await fetchWithTimeout(`${API_BASE}/bots/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bot)
    });
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${API_BASE}/bots/delete/${botId}`, {
      method: 'DELETE'
    });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
    if (res.ok) return true;
    return await getErrorMessage(res);
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
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return await res.json();
  }
};

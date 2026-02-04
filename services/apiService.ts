
import { BotConfig, User } from '../types';

const API_BASE = '/api';

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 30000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { 
      ...options, 
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {})
      }
    });
    clearTimeout(timer);
    return response;
  } catch (error: any) {
    clearTimeout(timer);
    throw error;
  }
};

export const api = {
  checkConnection: async () => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  getUser: async (userId: string): Promise<User | null> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/user/${userId}`, { method: 'GET' });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) throw new Error("Ошибка входа");
    return await response.json();
  },

  // Fix: Add missing requestVerification method
  requestVerification: async (email: string) => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/request-verification`, {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    if (!response.ok) {
        const data = await response.json();
        return data.message || "Ошибка отправки кода";
    }
    return true;
  },

  // Fix: Add missing verifyAndRegister method
  verifyAndRegister: async (data: any): Promise<User | null> => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/verify-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.message || "Ошибка регистрации");
    }
    return await response.json();
  },

  // Fix: Add missing forgotPassword method
  forgotPassword: async (email: string) => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    if (!response.ok) {
        const data = await response.json();
        return data.message || "Ошибка";
    }
    return true;
  },

  // Fix: Add missing resetPassword method
  resetPassword: async (data: any) => {
    const response = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.message || "Ошибка сброса пароля");
    }
    return true;
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    if (!userId) return [];
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`, { method: 'GET' });
      if (!response.ok) return [];
      const data = await response.json();
      return data.map((b: any) => ({ ...b, settings: b.config?.settings || b.settings, ...b.config }));
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig) => {
    await fetchWithTimeout(`${API_BASE}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
  },

  deleteBot: async (userId: string, bot_id: string) => {
    await fetchWithTimeout(`${API_BASE}/bots/delete/${userId}/${bot_id}`, { method: 'DELETE' });
  },

  startBotOnServer: async (bot: BotConfig) => {
    const response = await fetchWithTimeout(`${API_BASE}/bots/start`, {
      method: 'POST',
      body: JSON.stringify({ id: bot.id })
    });
    return response.ok;
  },

  stopBotOnServer: async (bot_id: string) => {
    await fetchWithTimeout(`${API_BASE}/bots/stop/${bot_id}`, { method: 'POST' });
  },

  getBotLogs: async (bot_id: string): Promise<string> => {
    const response = await fetchWithTimeout(`${API_BASE}/bots/logs/${bot_id}`, { method: 'GET' });
    const data = await response.json();
    return data.logs || "Логов нет.";
  },

  getBotMessages: async (bot_id: string): Promise<any[]> => {
    return []; // Заглушка, если эндпоинт еще не реализован полностью
  },

  sendBroadcast: async (botIds: string[], message: string) => {
    const response = await fetchWithTimeout(`${API_BASE}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message })
    });
    return response.ok ? await response.json() : null;
  },

  activateLicense: async (botId: string, key: string) => {
    const response = await fetchWithTimeout(`${API_BASE}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok ? await response.json() : { status: 'error' };
  }
};


import { BotConfig, User } from '../types';

const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  if (debugUrl) return `${debugUrl.replace(/\/$/, '')}/api`;
  return '/api';
};

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
      const res = await fetchWithTimeout(`${getApiBase()}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  getUser: async (userId: string): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/user/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) throw new Error("Login failed");
    return await response.json();
  },

  requestVerification: async (email: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    return response.ok;
  },

  verifyAndRegister: async (data: any): Promise<User> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error("Registration failed");
    return await response.json();
  },

  // Added: forgotPassword method for Auth component
  forgotPassword: async (email: string): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/forgot-password`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      return response.ok;
    } catch (e) { return false; }
  },

  // Added: resetPassword method for Auth component
  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/reset-password`, {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) { return false; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    if (!userId || userId === "new") return [];
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig) => {
    await fetchWithTimeout(`${getApiBase()}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
  },

  moderateUser: async (botId: string, userId: number, action: 'ban' | 'unban' | 'warn' | 'unwarn') => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/moderate`, {
        method: 'POST',
        body: JSON.stringify({ botId, userId, action })
    });
    return response.ok ? await response.json() : null;
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/delete/${userId}/${botId}`, { method: 'DELETE' });
  },

  startBotOnServer: async (bot: BotConfig) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify({ id: bot.id })
      });
      return response.ok ? true : 'Failed to start';
    } catch (err: any) { return err.message; }
  },

  stopBotOnServer: async (botId: string) => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, { method: 'POST' });
  },

  getBotLogs: async (botId: string): Promise<string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/logs/${botId}`, { method: 'GET' });
      const data = await response.json();
      return data.logs || "Логов пока нет.";
    } catch (e) { return "Ошибка связи."; }
  },

  getBotMessages: async (botId: string): Promise<any[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/messages/${botId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  sendBroadcast: async (botIds: string[], message: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message })
    });
    return response.ok ? await response.json() : null;
  },

  // Added: activateLicense method for Profile component
  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/activate-license`, {
        method: 'POST',
        body: JSON.stringify({ botId, key })
      });
      return response.ok ? await response.json() : { status: 'error', message: 'Failed to connect' };
    } catch (e) { return { status: 'error', message: 'Connection error' }; }
  }
};

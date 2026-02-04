
import { BotConfig, User } from '../types';
import { generatePythonCode } from './pythonGenerator';

const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  // Убираем возможный лишний слэш в конце
  const base = debugUrl ? debugUrl : '';
  return `${base}/api`;
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
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) throw new Error('Login failed');
    return await response.json();
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      return 'Server error (405 or other)';
    } catch (err: any) { return err.message; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/${userId}/${botId}`, { method: 'DELETE' });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const code = generatePythonCode(bot);
      const response = await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify({ id: bot.id, token: bot.token, code })
      });
      return response.ok ? true : 'Failed to start';
    } catch (err: any) { return err.message; }
  },

  stopBotOnServer: async (botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, { method: 'POST' });
  },

  getBotMessages: async (botId: string): Promise<any[]> => {
    return [];
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    const response = await fetchWithTimeout(`${getApiBase()}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok ? await response.json() : { status: 'error' };
  },

  verifyAndRegister: async (data: any): Promise<User> => ({ 
    id: 'new', 
    username: data.username || 'User', 
    email: data.email, 
    balance: 0,
    botsCreated: 0,
    licenseExpiresAt: Date.now() + 259200000
  }),
  
  // Fix: sendBroadcast now accepts botIds and message
  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ botIds, message })
      });
      return response.ok ? await response.json() : { success: 0, failed: botIds.length };
    } catch (e) {
      return null;
    }
  },

  // Fix: forgotPassword now accepts email
  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/forgot-password`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      return response.ok ? true : 'Server error';
    } catch (err: any) {
      return err.message;
    }
  },

  // Fix: resetPassword now accepts data object with email, code, and newPassword
  resetPassword: async (data: { email: string; code: string; newPassword: string }): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/reset-password`, {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) {
      return false;
    }
  },
};

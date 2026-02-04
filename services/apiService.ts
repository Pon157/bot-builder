
import { BotConfig, User } from '../types';
import { generatePythonCode } from './pythonGenerator';

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
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Login failed');
    }
    return await response.json();
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const err = await response.json();
      return err.detail || 'Error';
    } catch (err: any) { 
      return err.message; 
    }
  },

  verifyAndRegister: async (data: any): Promise<User> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Registration failed');
    }
    return await response.json();
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
    // Implement delete on backend if needed
    // await fetchWithTimeout(`${getApiBase()}/bots/${userId}/${botId}`, { method: 'DELETE' });
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

  // Fix: Added missing sendBroadcast method to match usage in BroadcastManager.tsx
  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ botIds, message })
      });
      if (response.ok) {
        return await response.json();
      }
      return null;
    } catch (e) {
      console.error('Broadcast Error:', e);
      return null;
    }
  },

  forgotPassword: async (email: string) => true,
  resetPassword: async (data: any) => true,
};

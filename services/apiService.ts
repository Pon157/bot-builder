
import { BotConfig, User } from '../types';
import { generatePythonCode } from './pythonGenerator';

const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  return debugUrl ? `${debugUrl}/api` : '/api';
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
    
    if (!response.ok) {
        const errorText = await getErrorMessage(response);
        throw new Error(errorText);
    }
    
    return response;
  } catch (error: any) {
    clearTimeout(timer);
    throw error;
  }
};

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    return data.detail || data.message || `Error ${response.status}`;
  } catch (e) {
    return `HTTP Error ${response.status}`;
  }
};

export const api = {
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetch(`${getApiBase()}/ping`);
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    return await response.json();
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      return response.ok;
    } catch (err: any) { throw err; }
  },

  verifyAndRegister: async (data: any): Promise<User> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify({
        email: data.email,
        username: data.username,
        password: data.password,
        code: data.code
      })
    });
    return await response.json();
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      return await response.json();
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

  stopBotOnServer: async (botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, { method: 'POST' });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const code = generatePythonCode(bot);
      await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify({
          id: bot.id,
          token: bot.token,
          code: code
        })
      });
      return true;
    } catch (err: any) { return err.message; }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message })
    });
    return await response.json();
  },

  getBotMessages: async (botId: string): Promise<any[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/messages/${botId}`, { method: 'GET' });
      return await response.json();
    } catch (e) { return []; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    const response = await fetchWithTimeout(`${getApiBase()}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return await response.json();
  },

  forgotPassword: async (email: string) => true,
  resetPassword: async (data: any) => true,
};

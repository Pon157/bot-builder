
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
        console.warn(`API Response Error: ${response.status} for ${url}`);
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
      const res = await fetchWithTimeout(`${getApiBase()}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) throw new Error(await getErrorMessage(response));
    return await response.json();
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      return response.ok;
    } catch (err: any) { return err.message; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      if (!response.ok) return [];
      return await response.json();
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
    if (!response.ok) throw new Error(await getErrorMessage(response));
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/${userId}/${botId}`, { method: 'DELETE' });
  },

  stopBotOnServer: async (botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, { method: 'POST' });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      // Ключевое изменение: передаем сгенерированный код на сервер
      const code = generatePythonCode(bot);
      const response = await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify({
          id: bot.id,
          token: bot.token,
          code: code
        })
      });
      if (response.ok) return true;
      return await getErrorMessage(response);
    } catch (err: any) { return err.message; }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message })
    });
    return response.ok ? await response.json() : null;
  },

  getBotMessages: async (botId: string): Promise<any[]> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/messages/${botId}`, { method: 'GET' });
    return response.ok ? await response.json() : [];
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    const response = await fetchWithTimeout(`${getApiBase()}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok ? await response.json() : { status: 'error' };
  },

  // Заглушки для предотвращения ошибок компиляции
  forgotPassword: async (email: string) => true,
  resetPassword: async (data: any) => true,
  // Fix: Return a full User object to satisfy the User interface requirements in components/Auth.tsx
  verifyAndRegister: async (data: any): Promise<User> => ({ 
    id: 'new', 
    username: data.username || 'User', 
    email: data.email, 
    balance: 0,
    botsCreated: 0,
    licenseExpiresAt: Date.now() + (3 * 24 * 3600 * 1000)
  })
};

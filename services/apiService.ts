
import { BotConfig, User } from '../types';

// По умолчанию используем относительный путь для проксирования через Nginx/Vite
const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  return debugUrl ? debugUrl + '/api' : '/api';
};

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 45000) => {
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
    
    if (response.status === 405) {
      console.error(`❌ 405 Method Not Allowed на URL: ${url}. 
      Метод: ${options.method || 'GET'}. 
      Если вы видите это в браузере, но curl работает — проверьте OPTIONS запросы и trailing slashes в Nginx.`);
    }
    
    return response;
  } catch (error: any) {
    clearTimeout(timer);
    if (error.name === 'AbortError') {
      throw new Error("Сервер не ответил вовремя (Таймаут)");
    }
    console.error(`🔌 Сетевая ошибка (${url}):`, error);
    throw error;
  }
};

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    return data.detail || data.message || "Ошибка сервера";
  } catch (e) {
    return `Ошибка ${response.status}`;
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
      if (response.ok) return true;
      return await getErrorMessage(response);
    } catch (err: any) {
      return err.message || "Ошибка соединения";
    }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error(await getErrorMessage(response));
    return await response.json();
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' }, 15000);
      if (!response.ok) return [];
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
    await fetchWithTimeout(`${getApiBase()}/bots/${userId}/${botId}`, {
      method: 'DELETE'
    });
  },

  stopBotOnServer: async (botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, {
      method: 'POST'
    });
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify(bot)
      });
      if (response.ok) return true;
      return await getErrorMessage(response);
    } catch (err: any) {
      return err.message || "Ошибка соединения";
    }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message })
    });
    if (!response.ok) throw new Error(await getErrorMessage(response));
    return await response.json();
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/forgot-password`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      return await getErrorMessage(response);
    } catch (err: any) {
      return err.message || "Ошибка соединения";
    }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/reset-password`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    return response.ok;
  },

  activateLicense: async (botId: string, key: string): Promise<{ status: string; newExpiry: number } | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/activate-license`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    if (!response.ok) return null;
    return await response.json();
  }
};

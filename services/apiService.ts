
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
        const err = await response.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(err.detail || 'Неверный Email или пароль');
    }
    const userData = await response.json();
    if (!userData || !userData.id) throw new Error("Сервер вернул пустой профиль");
    return userData;
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const err = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
      return err.detail || 'Error';
    } catch (err: any) { return err.message; }
  },

  verifyAndRegister: async (data: any): Promise<User> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Ошибка регистрации' }));
        throw new Error(err.detail || 'Registration failed');
    }
    const userData = await response.json();
    if (!userData || !userData.id) throw new Error("Ошибка БД: пользователь не создан");
    return userData;
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    // ЖЕСТКИЙ ПРЕДОХРАНИТЕЛЬ: никогда не делаем запрос, если userId некорректен
    if (!userId || userId === "new" || userId === "undefined" || userId === "null") {
      console.warn("apiService: Aborting getBots call due to invalid userId:", userId);
      return [];
    }
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { 
      console.error("apiService: Fetch bots error:", e);
      return []; 
    }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
    if (!response.ok) throw new Error("Не удалось сохранить бота");
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/delete/${userId}/${botId}`, { method: 'DELETE' });
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

  getBotMessages: async (botId: string): Promise<any[]> => [],

  activateLicense: async (botId: string, key: string): Promise<any> => {
    const response = await fetchWithTimeout(`${getApiBase()}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok ? await response.json() : { status: 'error' };
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<{ success: number; failed: number } | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ botIds, message })
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/forgot-password`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const err = await response.json();
      return err.detail || 'Error';
    } catch (err: any) { return err.message; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/reset-password`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Reset failed');
    }
    return true;
  },
};

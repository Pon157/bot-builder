
import { BotConfig, User } from '../types';

// Используем относительный путь, чтобы Nginx на порту 80/443 мог проксировать запросы
const API_BASE = '/api';

const fetchWithTimeout = async (path: string, options: any = {}) => {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE}${cleanPath}`;
  
  console.log(`📡 Sending ${options.method || 'GET'} to: ${url}`);

  try {
    const response = await fetch(url, { 
      ...options, 
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {})
      }
    });
    
    if (response.status === 405) {
      console.error(`❌ 405 Method Not Allowed на ${url}.`);
      console.log("%cРЕШЕНИЕ: Проверьте конфиг Nginx! Блок 'location ^~ /api/ { proxy_pass http://127.0.0.1:8000/api/; }' должен быть выше, чем 'location /'.", "color: orange; font-weight: bold;");
    }
    
    return response;
  } catch (error: any) {
    console.error(`❌ Network Error (${url}):`, error.message);
    throw error;
  }
};

export const api = {
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout('/ping', { method: 'GET' });
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    try {
      // Fix: replaced .strip() with .trim() as .strip() is not a native JS string method
      const response = await fetchWithTimeout('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: email.toLowerCase().trim(), password })
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) { return null; }
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      // Fix: replaced .strip() with .trim() as .strip() is not a native JS string method
      const response = await fetchWithTimeout('/auth/verify-request', {
        method: 'POST',
        body: JSON.stringify({ email: email.toLowerCase().trim() })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'Ошибка';
    } catch (e) { return 'Ошибка сети'; }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout('/auth/register', {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`/bots/${userId}`);
      if (!response.ok) return [];
      const rows = await response.json();
      return rows;
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetchWithTimeout('/bots/save', {
        method: 'POST',
        body: JSON.stringify(bot)
      });
    } catch (e) { console.error("Save error:", e); }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetchWithTimeout(`/bots/delete/${botId}`, { method: 'DELETE' });
    } catch (e) { console.error("Delete error:", e); }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`/bots/start/${bot.id}`, { method: 'POST' });
      if (res.ok) return true;
      const err = await res.json();
      return err.detail || "Error starting bot";
    } catch (e) { return "Network error"; }
  },

  stopBotOnServer: async (botId: string): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`/bots/stop/${botId}`, { method: 'POST' });
      return res.ok;
    } catch (e) { return false; }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout('/broadcast', {
        method: 'POST',
        body: JSON.stringify({ botIds, message })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout('/license/activate', {
        method: 'POST',
        body: JSON.stringify({ botId, key })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      // Fix: replaced .strip() with .trim() as .strip() is not a native JS string method
      const response = await fetchWithTimeout('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email: email.toLowerCase().trim() })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'Ошибка';
    } catch (e) { return 'Ошибка сети'; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout('/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) { return false; }
  },
};

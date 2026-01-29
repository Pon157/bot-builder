
import { BotConfig, User } from '../types';

const API_BASE = '/api';

const fetchWithTimeout = async (url: string, options: any = {}) => {
  // Убираем возможные двойные слеши и завершающие слеши (критично для Nginx POST)
  const cleanUrl = url.replace(/([^:]\/)\/+/g, "$1").replace(/\/$/, ""); 
  
  console.log(`📡 API Request: ${options.method || 'GET'} ${cleanUrl}`);

  try {
    const response = await fetch(cleanUrl, { 
      ...options, 
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {})
      }
    });
    
    if (response.status === 405) {
      console.error("❌ 405 Method Not Allowed! Проверьте конфиг Nginx (блок location /api/).");
    }
    
    return response;
  } catch (error: any) {
    console.error(`❌ Network Error:`, error.message);
    throw error;
  }
};

const DEFAULT_SETTINGS = {
  useTopics: false,
  topicPerRequest: false,
  forwardToAdmin: true,
  antiSpam: true,
  showUserInfo: true,
  showUsername: true,
  autoApproveJoin: false,
  rateLimit: 15,
  autoBanThreshold: 0
};

export const api = {
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/ping`, { method: 'GET' });
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (e) { return null; }
  },

  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/verify-request`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'Ошибка отправки';
    } catch (e) { return 'Ошибка сети'; }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/register`, {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      const rows = await response.json();
      return rows.map((row: any) => ({
        ...row,
        ...row.config,
        ownerId: row.owner_id,
        licenseExpiresAt: row.license_expires_at,
        settings: { ...DEFAULT_SETTINGS, ...(row.config?.settings || {}) },
        stats: row.stats || { totalMessages: 0, incomingToday: 0, outgoingToday: 0, history: [] },
        connectedUsers: row.config?.connectedUsers || [],
        logs: row.config?.logs || []
      }));
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/save`, {
        method: 'POST',
        body: JSON.stringify(bot)
      });
    } catch (e) { console.error("Save error:", e); }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/delete/${botId}`, { method: 'DELETE' });
    } catch (e) { console.error("Delete error:", e); }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
      if (res.ok) return true;
      const err = await res.json();
      return err.detail || "Error starting bot";
    } catch (e) { return "Network error"; }
  },

  stopBotOnServer: async (botId: string): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/stop/${botId}`, { method: 'POST' });
      return res.ok;
    } catch (e) { return false; }
  },

  sendBroadcast: async (botIds: string[], message: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ botIds, message })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/license/activate`, {
        method: 'POST',
        body: JSON.stringify({ botId, key })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'Ошибка';
    } catch (e) { return 'Ошибка сети'; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) { return false; }
  },
};

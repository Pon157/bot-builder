
import { BotConfig, User } from '../types';

const API_BASE = (import.meta as any).env?.VITE_API_URL || 
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? `${window.location.protocol}//${window.location.hostname}:8000/api` 
    : `${window.location.origin}/api`);

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 15000) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
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
      const res = await fetchWithTimeout(`${API_BASE}/ping`, { method: 'GET' }, 3000);
      return res.ok;
    } catch (e) { return false; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  // FIX: Added missing authentication methods
  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/verify-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'Error sending code';
    } catch (e) { return 'Connection error'; }
  },

  verifyAndRegister: async (data: any): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (response.ok) return true;
      const data = await response.json();
      return data.detail || 'User not found';
    } catch (e) { return 'Connection error'; }
  },

  resetPassword: async (data: any): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return response.ok;
    } catch (e) { return false; }
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/bots/${userId}`);
      if (!response.ok) return [];
      const rows = await response.json();
      return rows.map((row: any) => {
        const config = row.config || {};
        return {
          ...row,
          ...config,
          ownerId: row.owner_id,
          licenseExpiresAt: row.license_expires_at,
          settings: { ...DEFAULT_SETTINGS, ...(config.settings || {}) },
          stats: row.stats || { totalMessages: 0, incomingToday: 0, outgoingToday: 0, history: [] },
          connectedUsers: config.connectedUsers || [],
          triggers: config.triggers || [],
          buttons: config.buttons || [],
          logs: config.logs || []
        };
      });
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    try {
      // Сервер ожидает ownerId и id в корне, остальное в конфиге (сервер сам разложит)
      await fetchWithTimeout(`${API_BASE}/bots/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bot)
      });
    } catch (e) { console.error("API Error: Failed to save bot"); }
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    try {
      await fetchWithTimeout(`${API_BASE}/bots/delete/${botId}`, { method: 'DELETE' });
    } catch (e) { console.error("API Error: Failed to delete bot"); }
  },

  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/bots/start/${bot.id}`, { method: 'POST' });
      if (res.ok) return true;
      const err = await res.json();
      return err.detail || "Error";
    } catch (e) { return "Network Error"; }
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ botIds, message })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  },

  activateLicense: async (botId: string, key: string): Promise<any> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ botId, key })
      });
      return res.ok ? await res.json() : null;
    } catch (e) { return null; }
  }
};

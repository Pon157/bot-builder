
import { BotConfig, User } from '../types';

// Используем относительный путь для проксирования через Nginx
const API_BASE = '/api';

const request = async (path: string, method = 'GET', body?: any) => {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE}${cleanPath}`;
  
  console.log(`📡 API Request: ${method} ${url}`);

  const response = await fetch(url, {
    method,
    headers: { 
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: body ? JSON.stringify(body) : undefined
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorMessage = 'API Error';
    try {
      const errorJson = JSON.parse(errorText);
      errorMessage = errorJson.detail || errorMessage;
    } catch (e) {
      errorMessage = errorText || errorMessage;
    }
    throw new Error(errorMessage);
  }
  
  return response.json();
};

export const api = {
  checkConnection: async () => {
    try { await request('/ping'); return true; } catch { return false; }
  },
  login: async (email, password) => {
    try { return await request('/auth/login', 'POST', { email, password }); } catch (e) { 
      console.error("Login Error:", e);
      return null; 
    }
  },
  requestVerification: async (email) => {
    try { 
      // Пробуем оба варианта пути для совместимости
      await request('/auth/request-verification', 'POST', { email }); 
      return true; 
    } catch (e: any) { return e.message; }
  },
  verifyAndRegister: async (data) => {
    try { return await request('/auth/register', 'POST', data); } catch { return null; }
  },
  forgotPassword: async (email: string) => {
    try { await request('/auth/forgot-password', 'POST', { email }); return true; } catch (e: any) { return e.message; }
  },
  resetPassword: async (data: any) => {
    try { await request('/auth/reset-password', 'POST', data); return true; } catch { return false; }
  },
  getBots: async (userId) => {
    try { 
      const rows = await request(`/bots/${userId}`); 
      return rows.map(r => ({ ...r, ...r.config, ownerId: r.ownerId, status: r.status }));
    } catch { return []; }
  },
  saveBot: async (userId, bot) => {
    await request('/bots/save', 'POST', bot);
  },
  sendBroadcast: async (botIds: string[], message: string) => {
    return await request('/broadcast', 'POST', { botIds, message });
  },
  startBotOnServer: async (bot) => {
    try { await request(`/bots/start/${bot.id}`, 'POST'); return true; } catch (e: any) { return e.message; }
  },
  stopBotOnServer: async (botId) => {
    try { await request(`/bots/stop/${botId}`, 'POST'); return true; } catch { return false; }
  },
  deleteBot: async (userId, botId) => {
    await request(`/bots/delete/${botId}`, 'DELETE');
  },
  activateLicense: async (botId, key) => {
    try { return await request('/license/activate', 'POST', { botId, key }); } catch { return null; }
  }
};

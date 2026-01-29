
import { BotConfig, User } from '../types';

// Используем URL из переменной окружения, если она есть, иначе относительный путь
const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api';

const request = async (path: string, method = 'GET', body?: any) => {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  // Убеждаемся, что URL не содержит двойных слешей, если API_BASE заканчивается на /
  const url = `${API_BASE.replace(/\/$/, '')}${cleanPath}`;
  
  try {
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
      let errorMessage = `Error ${response.status}`;
      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.detail || errorMessage;
      } catch (e) {
        errorMessage = errorText || errorMessage;
      }
      throw new Error(errorMessage);
    }
    
    return response.json();
  } catch (e: any) {
    console.error(`API Request Failed [${method} ${url}]:`, e);
    throw e;
  }
};

export const api = {
  checkConnection: async () => {
    try { 
      const res = await request('/ping'); 
      return res && res.status === 'ok';
    } catch { 
      return false; 
    }
  },
  login: async (email, password) => {
    return await request('/auth/login', 'POST', { email, password });
  },
  requestVerification: async (email) => {
    try { 
      await request('/auth/request-verification', 'POST', { email }); 
      return true; 
    } catch (e: any) { 
      return e.message; 
    }
  },
  verifyAndRegister: async (data) => {
    return await request('/auth/verify-and-register', 'POST', data); 
  },
  getBots: async (userId) => {
    try { 
      return await request(`/bots/${userId}`); 
    } catch { 
      return []; 
    }
  },
  saveBot: async (userId, bot) => {
    await request('/bots/save', 'POST', bot);
  },
  startBotOnServer: async (bot) => {
    try { 
      await request(`/bots/start/${bot.id}`, 'POST'); 
      return true; 
    } catch (e: any) { 
      return e.message; 
    }
  },
  stopBotOnServer: async (botId) => {
    try { 
      await request(`/bots/stop/${botId}`, 'POST'); 
      return true; 
    } catch { 
      return false; 
    }
  },
  deleteBot: async (userId, botId) => {
    await request(`/bots/delete/${botId}`, 'DELETE');
  },
  activateLicense: async (botId, key) => {
    try { 
      return await request('/license/activate', 'POST', { botId, key }); 
    } catch { 
      return null; 
    }
  },
  // Added missing sendBroadcast method to fix compilation error in components/BroadcastManager.tsx
  sendBroadcast: async (botIds: string[], message: string) => {
    return await request('/broadcast/send', 'POST', { botIds, message });
  },
  // Added missing forgotPassword method to fix compilation error in components/Auth.tsx
  forgotPassword: async (email: string) => {
    try {
      await request('/auth/forgot-password', 'POST', { email });
      return true;
    } catch (e: any) {
      return e.message;
    }
  },
  // Added missing resetPassword method to fix compilation error in components/Auth.tsx
  resetPassword: async (data: any) => {
    try {
      await request('/auth/reset-password', 'POST', data);
      return true;
    } catch {
      return false;
    }
  }
};

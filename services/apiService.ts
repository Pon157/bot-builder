
import { BotConfig, User } from '../types';

// Если мы на продакшене, используем текущий домен, если в разработке - localhost
const API_BASE = '/api'; 

const request = async (path: string, method = 'GET', body?: any) => {
  const url = `${API_BASE}/${path.startsWith('/') ? path.slice(1) : path}`;
  
  try {
    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error(err || `Status ${response.status}`);
    }
    return response.json();
  } catch (e: any) {
    console.error(`API Error on ${url}:`, e);
    throw e;
  }
};

export const api = {
  checkConnection: async () => {
    try {
      const res = await request('ping');
      return res && res.status === 'online';
    } catch {
      return false;
    }
  },
  login: async (email, password) => request('auth/login', 'POST', { email, password }),
  requestVerification: async (email) => {
    try { await request('auth/request-verification', 'POST', { email }); return true; }
    catch (e: any) { return e.message; }
  },
  verifyAndRegister: async (data) => request('auth/verify-and-register', 'POST', data),
  getBots: async (uid) => request(`bots/${uid}`),
  saveBot: async (uid, bot) => request('bots/save', 'POST', bot),
  startBotOnServer: async (bot) => {
    try { await request(`bots/start/${bot.id}`, 'POST'); return true; }
    catch (e: any) { return e.message; }
  },
  stopBotOnServer: async (bid) => {
    try { await request(`bots/stop/${bid}`, 'POST'); return true; }
    catch { return false; }
  },
  deleteBot: async (uid, bid) => request(`bots/delete/${bid}`, 'DELETE'),
  sendBroadcast: async (botIds, message) => request('broadcast', 'POST', { botIds, message }),
  forgotPassword: async (email) => {
    try { await request('auth/forgot-password', 'POST', { email }); return true; }
    catch (e: any) { return e.message; }
  },
  resetPassword: async (data) => {
    try { await request('auth/reset-password', 'POST', data); return true; }
    catch { return false; }
  },
  activateLicense: async (bid, key) => request('license/activate', 'POST', { botId: bid, key })
};

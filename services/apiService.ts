
import { BotConfig, User } from '../types';

const API_BASE = '/api';

const request = async (path: string, method = 'GET', body?: any) => {
  const url = `${API_BASE}${path.startsWith('/') ? path : '/' + path}`;
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Network error' }));
    throw new Error(error.detail || 'API Error');
  }
  return response.json();
};

export const api = {
  checkConnection: async () => {
    try { await request('/ping'); return true; } catch { return false; }
  },
  login: async (email, password) => {
    try { return await request('/auth/login', 'POST', { email, password }); } catch { return null; }
  },
  requestVerification: async (email) => {
    try { await request('/auth/verify-request', 'POST', { email }); return true; } catch (e: any) { return e.message; }
  },
  verifyAndRegister: async (data) => {
    try { return await request('/auth/register', 'POST', data); } catch { return null; }
  },
  // Added forgotPassword method to handle password recovery requests
  forgotPassword: async (email: string) => {
    try { await request('/auth/forgot-password', 'POST', { email }); return true; } catch (e: any) { return e.message; }
  },
  // Added resetPassword method to finalize password reset with a code
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
  // Added sendBroadcast method for global messaging across multiple bots
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

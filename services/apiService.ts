import { BotConfig, User } from '../types';

const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  if (debugUrl) return `${debugUrl.replace(/\/$/, '')}/api`;
  return '/api';
};

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 30000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  
  // Определяем заголовки по умолчанию
  const defaultHeaders: any = {
    'Accept': 'application/json',
  };

  // Если мы НЕ отправляем FormData, добавляем Content-Type: application/json
  if (!(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  try {
    const response = await fetch(url, { 
      ...options, 
      signal: controller.signal,
      headers: {
        ...defaultHeaders,
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
  checkConnection: async () => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  // --- НОВЫЙ МЕТОД ДЛЯ ЗАГРУЗКИ ФОТО ---
  uploadFile: async (file: File): Promise<{ url: string } | null> => {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetchWithTimeout(`${getApiBase()}/upload`, {
        method: 'POST',
        body: formData,
        // Мы НЕ передаем заголовки здесь, fetchWithTimeout сам поймет, 
        // что для FormData не нужно ставить application/json
      });

      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Upload error:", e);
      return null;
    }
  },

  getUser: async (userId: string): Promise<User | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/auth/user/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  login: async (email: string, password: string): Promise<User | null> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) throw new Error("Неверный логин/пароль");
    return await response.json();
  },

  requestVerification: async (email: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/request-verification`, {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    return response.ok;
  },

  verifyAndRegister: async (data: any): Promise<User> => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/verify-and-register`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error("Registration failed");
    return await response.json();
  },

  forgotPassword: async (email: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/forgot-password`, {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    return response.ok;
  },

  resetPassword: async (data: any) => {
    const response = await fetchWithTimeout(`${getApiBase()}/auth/reset-password`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    return response.ok;
  },

  getBots: async (userId: string): Promise<BotConfig[]> => {
    if (!userId || userId === "new") return [];
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  saveBot: async (userId: string, bot: BotConfig) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/save`, {
      method: 'POST',
      body: JSON.stringify(bot)
    });
    return response.ok ? await response.json() : null;
  },

  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await fetchWithTimeout(`${getApiBase()}/bots/delete/${userId}/${botId}`, { method: 'DELETE' });
  },

  startBotOnServer: async (bot: BotConfig) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/start`, {
        method: 'POST',
        body: JSON.stringify({ id: bot.id })
      });
      return response.ok ? true : 'Failed to start';
    } catch (err: any) { return err.message; }
  },

  stopBotOnServer: async (botId: string) => {
    await fetchWithTimeout(`${getApiBase()}/bots/stop/${botId}`, { method: 'POST' });
  },

  getBotLogs: async (botId: string): Promise<string> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/logs/${botId}`, { method: 'GET' });
      const data = await response.json();
      return data.logs || "Логов пока нет.";
    } catch (e) { return "Ошибка связи."; }
  },

  getBotMessages: async (botId: string): Promise<any[]> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/messages/${botId}`, { method: 'GET' });
      return response.ok ? await response.json() : [];
    } catch (e) { return []; }
  },

  activateLicense: async (botId: string, key: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/license/activate`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok ? await response.json() : { status: 'error' };
  },

  getBotStats: async (botId: string): Promise<any> => {
  try {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/stats/${botId}`, { method: 'GET' });
    if (!response.ok) return { stats: { total_messages: 0, active_users: 0 } }; // Заглушка при ошибке
    return await response.json();
  } catch (e) { 
    return { stats: { total_messages: 0, active_users: 0 } }; 
  }
},

  // Обновленный sendBroadcast с поддержкой фото
  sendBroadcast: async (botIds: string[], message: string, photoUrl?: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message, photo_url: photoUrl })
    });
    return response.ok ? await response.json() : null;
  },
  // --- ADMIN API ---
adminLogin: async (login: string, pass: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/login`, {
      method: 'POST',
      body: JSON.stringify({ login, password: pass })
    });
    if (!response.ok) throw new Error("Неверный логин или пароль");
    const data = await response.json();
    
    // Сохраняем токен сразу, чтобы не потерять при редиректе
    if (data.token) {
        localStorage.setItem('admin_token', data.token);
    }
    return data; 
  },

  getAdminDashboard: async (token: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/dashboard`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    if (!response.ok) throw new Error("Unauthorized");
    return response.json();
  },

  getAllUsers: async (token: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/users`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.json();
  },

  getAllBots: async (token: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bots`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.json();
  },

  // Новый метод: Бан пользователя
  adminBanUser: async (token: string, userId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/user/ban`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ user_id: userId })
    });
    return response.ok;
  },

  // Улучшенный метод: Управление ботами (теперь поддерживает start)
  adminBotAction: async (token: string, botId: string, action: 'stop' | 'delete' | 'start') => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/action`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ bot_id: botId, action })
    });
    return response.ok;
  },

  // Прямой старт бота (через передачу объекта)
  adminStartBotDirect: async (token: string, botConfig: BotConfig) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bots/start`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ bot: botConfig })
    });
    return response.json();
  },
  
  generateKey: async (token: string, months: number, days: number) => {
     const response = await fetchWithTimeout(`${getApiBase()}/admin/generate-key`, {
        method: 'POST',
        headers: { 'x-admin-token': token },
        body: JSON.stringify({ months, days })
     });
     return response.json();
  },

  // Создание временного доступа для админа (Support Mode)
  createTempAccess: async (botId: string, key: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/temp-access`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok;
  },
  // Получить реальные логи сообщений
  getSystemLogs: async (token: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/system-logs`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.json();
  },

  // Бан/Разбан (обновленный)
  adminToggleBan: async (token: string, userId: string, isBanned: boolean) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/user/ban`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ user_id: userId, is_banned: isBanned })
    });
    return response.ok;
  },

  // Получить бота от имени Админа
  getBotAsAdmin: async (token: string, botId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/${botId}`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.ok ? await response.json() : null;
  },

  // Сохранить бота от имени Админа
  saveBotAsAdmin: async (token: string, bot: any) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/save`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify(bot)
    });
    return response.ok ? await response.json() : null;
  }
};

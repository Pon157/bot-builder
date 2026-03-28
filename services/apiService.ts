import { BotConfig, User } from '../types';

const getApiBase = () => {
  const debugUrl = localStorage.getItem('DEBUG_API_URL');
  if (debugUrl) return `${debugUrl.replace(/\/$/, '')}/api`;
  return '/api';
};

const fetchWithTimeout = async (url: string, options: any = {}, timeout = 30000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  
  const defaultHeaders: any = {
    'Accept': 'application/json',
  };

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

/**
 * Безопасно парсит JSON из ответа.
 * Если сервер вернул не-JSON (например, 502 от nginx или HTML-страницу ошибки) —
 * возвращает null вместо того чтобы упасть с SyntaxError.
 */
const safeJson = async (response: Response): Promise<any> => {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
};

export const api = {
  checkConnection: async () => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/ping`, { method: 'GET' }, 5000);
      return res.ok;
    } catch (e) { return false; }
  },

  uploadFile: async (file: File): Promise<{ url: string } | null> => {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${getApiBase()}/chat/media/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Ошибка загрузки:", e);
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
      if (!response.ok) return { stats: { total_messages: 0, active_users: 0 } };
      return await response.json();
    } catch (e) { 
      return { stats: { total_messages: 0, active_users: 0 } }; 
    }
  },

  sendBroadcast: async (botIds: string[], message: string, photoUrl?: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ botIds, message, photo_url: photoUrl })
    });
    return response.ok ? await response.json() : null;
  },

  // ── СТАФФ-СИСТЕМА ──────────────────────────────────────────────────

  getStaffStats: async (botId: string): Promise<{ staffAdmins: any[] }> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${botId}/staff/stat`, { method: 'GET' });
      return response.ok ? await response.json() : { staffAdmins: [] };
    } catch { return { staffAdmins: [] }; }
  },

  toggleStaffRest: async (botId: string, staffId: string, isOnRest: boolean, restUntil?: number): Promise<{ ok: boolean } | null> => {
    try {
      const body: Record<string, unknown> = { is_on_rest: isOnRest };
      if (restUntil) body.rest_until = restUntil;
      const response = await fetchWithTimeout(
        `${getApiBase()}/bots/${botId}/staff/${staffId}/rest`,
        { method: 'POST', body: JSON.stringify(body) }
      );
      return response.ok ? await response.json() : null;
    } catch { return null; }
  },

  getStaffAdminStat: async (botId: string, staffId: string): Promise<any | null> => {
    try {
      const response = await fetchWithTimeout(
        `${getApiBase()}/bots/${botId}/staff/stat?staff_id=${encodeURIComponent(staffId)}`,
        { method: 'GET' }
      );
      return response.ok ? await response.json() : null;
    } catch { return null; }
  },

  updateStaffStat: async (
    botId: string,
    staffId: string,
    event: 'accepted' | 'closed' | 'message' | 'response_ms',
    value = 1
  ): Promise<boolean> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/${botId}/staff/stat`, {
        method: 'POST',
        body: JSON.stringify({ staff_id: staffId, event, value })
      });
      return response.ok;
    } catch { return false; }
  },

  // ── конец СТАФФ-СИСТЕМЫ ────────────────────────────────────────────

  // --- ADMIN API ---
  adminLogin: async (login: string, pass: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/login`, {
      method: 'POST',
      body: JSON.stringify({ login, password: pass })
    });
    if (!response.ok) throw new Error("Неверный логин или пароль");
    const data = await response.json();
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

  adminBanUser: async (token: string, userId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/user/ban`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ user_id: userId })
    });
    return response.ok;
  },

  adminBotAction: async (token: string, botId: string, action: 'stop' | 'delete' | 'start') => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/action`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ bot_id: botId, action })
    });
    return response.ok;
  },

  adminStartBotDirect: async (token: string, botConfig: BotConfig) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bots/start`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ bot: botConfig })
    });
    return response.json();
  },
  
  generateKey: async (token: string, months: number, botName: string) => {
    console.log("🚀 Отправка названия бота на сервер:", botName);
    const response = await fetchWithTimeout(`${getApiBase()}/admin/generate_key`, {
      method: 'POST',
      headers: { 
        'x-admin-token': token,
        'Content-Type': 'application/json' 
      },
      body: JSON.stringify({ 
        months: months, 
        bot_id: botName 
      })
    });
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Ошибка сервера");
    }
    return await response.json();
  },

  createTempAccess: async (botId: string, key: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/temp-access`, {
      method: 'POST',
      body: JSON.stringify({ botId, key })
    });
    return response.ok;
  },

  getSystemLogs: async (token: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/system-logs`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.json();
  },

  getApplications: async (token: string) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/applications/list`, {
        method: 'GET',
        headers: { 'x-admin-token': token }
      });
      return response.ok ? await response.json() : [];
    } catch { return []; }
  },

  adminToggleBan: async (token: string, userId: string, isBanned: boolean) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/user/ban`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify({ user_id: userId, is_banned: isBanned })
    });
    return response.ok;
  },

  getBotAsAdmin: async (token: string, botId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/${botId}`, {
      method: 'GET',
      headers: { 'x-admin-token': token }
    });
    return response.ok ? await response.json() : null;
  },

  verifyAccessKey: async (key: string, botId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/verify_access_key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key.trim(), bot_id: botId })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || "Неверный ключ доступа");
    }

    return await response.json();
  },

  saveBotAsAdmin: async (token: string, bot: any) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/bot/save`, {
      method: 'POST',
      headers: { 'x-admin-token': token },
      body: JSON.stringify(bot)
    });
    return response.ok ? await response.json() : null;
  },

  // --- VK SPECIFIC ---
  
  getVkGroupInfo: async (token: string, groupId: string) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/vk/group-info`, {
        method: 'POST',
        body: JSON.stringify({ token, group_id: groupId })
      });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  testVkConnection: async (botId: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/vk-test/${botId}`, { method: 'GET' });
    return response.ok ? await response.json() : { status: 'error' };
  },

  sendVkMessage: async (botId: string, peerId: number, message: string, replyTo?: number) => {
    const response = await fetchWithTimeout(`${getApiBase()}/bots/vk-send`, {
      method: 'POST',
      body: JSON.stringify({ bot_id: botId, peer_id: peerId, message, reply_to: replyTo })
    });
    return response.ok;
  },

  // --- AI KEYS MANAGEMENT ---
  
  getAiKeys: async () => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/ai-keys`, { 
      method: 'GET',
      headers: {
        'x-admin-token': localStorage.getItem('ADMIN_SECRET') || ''
      }
    });
    if (!response.ok) return [];
    return await response.json();
  },

  checkAiKeyStatus: async (key: string) => {
    const response = await fetchWithTimeout(`${getApiBase()}/admin/ai-key-info/${key}`, { method: 'GET' });
    return response.ok ? await response.json() : null;
  },

  submitReview: async (reviewData: { name: string, role: string, text: string, rating: number }) => {
    try {
      const response = await fetch(`${getApiBase()}/reviews/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reviewData)
      });
      return response.ok;
    } catch (e) {
      console.error("Review submit error:", e);
      return false;
    }
  },

  getApprovedReviews: async () => {
    try {
      const response = await fetch(`${getApiBase()}/reviews/list`);
      if (!response.ok) return [];
      return await response.json();
    } catch (e) {
      console.error("Get reviews error:", e);
      return [];
    }
  },

  // --- MINI APPS ---
  saveMiniApp: async (appData: any) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/miniapps/save`, {
        method: 'POST',
        body: JSON.stringify({
          id: appData.id,
          owner_id: appData.owner_id,
          title: appData.title || 'Без названия',
          theme: appData.theme,
          components: appData.components,
          form_webhook: appData.formWebhook || ''
        })
      });
      return response.ok;
    } catch (e) {
      console.error("Ошибка при сохранении MiniApp:", e);
      return false;
    }
  },

  getMiniApp: async (appId: string) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/miniapps/${appId}`);
      if (!response.ok) return null;
      return await response.json();
    } catch (e) {
      console.error("Ошибка при загрузке MiniApp:", e);
      return null;
    }
  },
  
  listMiniApps: async (botId: string) => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/miniapps/list-by-bot/${botId}`);
      if (!res.ok) return [];
      return await res.json();
    } catch (e) { console.error("listMiniApps error:", e); return []; }
  },

  getMiniAppLicense: async (botId: string) => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/miniapps/license/${botId}`);
      if (!res.ok) return { active: false };
      return await res.json();
    } catch (e) { return { active: false }; }
  },

  activateMiniAppKey: async (key: string, botId: string) => {
    try {
      const res = await fetchWithTimeout(`${getApiBase()}/miniapps/activate`, {
        method: 'POST',
        body: JSON.stringify({ key, botId })
      });
      return await res.json();
    } catch (e) { return { status: 'error', message: 'Ошибка сети' }; }
  },

  submitForm: async (appId: string, formData: any) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/forms/submit`, {
        method: 'POST',
        body: JSON.stringify({ app_id: appId, form_data: formData })
      });
      return await response.json();
    } catch (e) {
      console.error("submitForm error:", e);
      return { ok: false, error: 'Ошибка сети' }; 
    }
  },

  // ─── CHAT PLATFORM ─────────────────────────────────────────────────────────

  chatSites: {
    list: async (ownerId: string) => {
      try {
        const res = await fetchWithTimeout(`${getApiBase()}/chat/sites/owner/${ownerId}`);
        return res.ok ? await res.json() : [];
      } catch { return []; }
    },
    create: async (ownerId: string, name: string, adminLogin?: string, adminPassword?: string) => {
      try {
        const res = await fetchWithTimeout(`${getApiBase()}/chat/sites`, {
          method: 'POST',
          body: JSON.stringify({ owner_id: ownerId, name, admin_login: adminLogin, admin_password: adminPassword })
        });
        return res.ok ? await res.json() : null;
      } catch { return null; }
    },
    update: async (siteId: string, ownerId: string, payload: object) => {
      try {
        const res = await fetchWithTimeout(`${getApiBase()}/chat/sites/${siteId}`, {
          method: 'PATCH',
          body: JSON.stringify({ owner_id: ownerId, ...payload })
        });
        return res.ok;
      } catch { return false; }
    },
    delete: async (siteId: string, ownerId: string) => {
      try {
        const res = await fetchWithTimeout(`${getApiBase()}/chat/sites/${siteId}?owner_id=${ownerId}`, { method: 'DELETE' });
        return res.ok;
      } catch { return false; }
    },
  },

  // ─── Баланс и транзакции ─────────────────────────────────────────────────────

  getBalance: async (userId: string): Promise<{ balance: number; transactions: any[] }> => {
    try {
      const r = await fetchWithTimeout(`${getApiBase()}/payments/balance/${userId}`);
      if (!r.ok) return { balance: 0, transactions: [] };
      return await r.json();
    } catch { return { balance: 0, transactions: [] }; }
  },

  getPrices: async (): Promise<any[]> => {
    try {
      const r = await fetchWithTimeout(`${getApiBase()}/payments/prices`);
      return r.ok ? await r.json() : [];
    } catch { return []; }
  },

  initiateTopup: async (userId: string, amount: number): Promise<{ payment_url?: string; label?: string; detail?: string } | null> => {
    try {
      const r = await fetchWithTimeout(`${getApiBase()}/payments/initiate`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, amount })
      });
      const data = await safeJson(r);
      if (!r.ok) {
        throw new Error(data?.detail || `Ошибка при создании платежа (${r.status})`);
      }
      return data;
    } catch (error: any) {
      console.error("API Error [initiateTopup]:", error);
      throw error;
    }
  },

  /**
   * Покупка услуги за баланс.
   *
   * Коды ответов сервера:
   *   200 — успех, возвращает { status, new_balance, expires_at, ... }
   *   402 — недостаточно средств
   *   404 — пользователь или услуга не найдены
   *   500 — ошибка БД
   *
   * Метод всегда бросает исключение при ошибке, так что вызывающий код
   * должен использовать try/catch и показывать e.message пользователю.
   */
  buyService: async (userId: string, serviceKey: string, targetId: string): Promise<any> => {
    let r: Response;
    try {
      r = await fetchWithTimeout(`${getApiBase()}/payments/buy`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, service_key: serviceKey, target_id: targetId })
      });
    } catch (networkError: any) {
      // Потеря сети, таймаут, CORS и т.д.
      throw new Error('Нет соединения с сервером. Проверьте интернет и попробуйте снова.');
    }

    // Пробуем прочитать тело — сервер может вернуть HTML при 502/504
    const data = await safeJson(r);

    if (!r.ok) {
      // Формируем внятное сообщение из ответа сервера
      const serverMessage: string =
        data?.detail ||
        data?.message ||
        data?.error ||
        `Ошибка сервера (${r.status})`;

      // Для 402 добавляем подсказку про пополнение баланса
      if (r.status === 402) {
        throw new Error(`${serverMessage}. Пополните баланс в разделе Профиль.`);
      }

      throw new Error(serverMessage);
    }

    return data;
  },

  adminGetAdPosts: async (token: string, status: string = 'pending') => {
    const r = await fetchWithTimeout(
      `${getApiBase()}/admin/ads/posts?status=${status}`,
      { method: 'GET', headers: { 'X-Admin-Token': token } }
    );
    return r.ok ? await r.json() : [];
  },

  adminApproveAdPost: async (token: string, postId: string) => {
    const r = await fetchWithTimeout(
      `${getApiBase()}/admin/ads/posts/${postId}/approve`,
      { method: 'POST', headers: { 'X-Admin-Token': token } }
    );
    return r.ok;
  },

  adminRejectAdPost: async (token: string, postId: string, reason: string) => {
    const r = await fetchWithTimeout(
      `${getApiBase()}/admin/ads/posts/${postId}/reject`,
      { method: 'POST', headers: { 'X-Admin-Token': token }, body: JSON.stringify({ reason }) }
    );
    return r.ok;
  },

  adminGetAdsStats: async (token: string) => {
    const r = await fetchWithTimeout(
      `${getApiBase()}/admin/ads/stats`,
      { method: 'GET', headers: { 'X-Admin-Token': token } }
    );
    return r.ok ? await r.json() : null;
  },

  // --- РЕФЕРАЛЬНАЯ СИСТЕМА ---

  getReferralStats: async (userId: string) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/referrals/stats/${userId}`, { method: 'GET' });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },

  getReferrerByCode: async (code: string) => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/referrals/referrer/${code}`, { method: 'GET' });
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
  },
  
  // --- BOT MANAGEMENT ---

  createBot: async (
    userId: string,
    name: string,
    token: string
  ): Promise<BotConfig | null> => {
    try {
      const response = await fetchWithTimeout(`${getApiBase()}/bots/create`, {
        method: 'POST',
        body: JSON.stringify({
          owner_id: userId,
          name,
          token,
          platform: 'telegram',
          adminIds:   [],
          channelId:  '',
          lotChannel: '',
          botLink:    '',
        })
      });
      return response.ok ? await response.json() : null;
    } catch (e) {
      console.error("Create bot error:", e);
      return null;
    }
  }
};

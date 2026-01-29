
import { BotConfig, User } from '../types';

/**
 * apiService.ts
 * Сервис для взаимодействия с FastAPI бэкендом.
 * Автоматически подстраивается под VITE_API_URL или использует относительные пути.
 */

const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api';

const request = async (path: string, method = 'GET', body?: any) => {
  // Очистка путей для предотвращения двойных слешей
  const cleanPath = path.startsWith('/') ? path.slice(1) : path;
  const cleanBase = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
  const url = `${cleanBase}/${cleanPath}`;
  
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
      let errorMessage = `Ошибка ${response.status}`;
      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.detail || errorMessage;
      } catch (e) {
        if (errorText.includes('nginx')) {
          errorMessage = 'Nginx вернул ошибку. Проверьте конфигурацию прокси (404/405).';
        } else {
          errorMessage = errorText || errorMessage;
        }
      }
      throw new Error(errorMessage);
    }
    
    return response.json();
  } catch (e: any) {
    console.error(`[API Request Failed] ${method} ${url}:`, e);
    throw e;
  }
};

export const api = {
  /** Проверка связи с бэкендом */
  checkConnection: async (): Promise<boolean> => {
    try {
      const res = await request('ping');
      return res && res.status === 'online';
    } catch (e) { 
      return false; 
    }
  },

  /** Авторизация */
  login: async (email, password): Promise<User> => {
    return await request('auth/login', 'POST', { email, password });
  },

  /** Запрос кода верификации (регистрация) */
  requestVerification: async (email: string): Promise<boolean | string> => {
    try {
      await request('auth/request-verification', 'POST', { email });
      return true;
    } catch (e: any) {
      return e.message;
    }
  },

  /** Верификация и создание аккаунта */
  verifyAndRegister: async (data: any): Promise<User> => {
    return await request('auth/verify-and-register', 'POST', data);
  },

  /** Запрос кода восстановления пароля */
  forgotPassword: async (email: string): Promise<boolean | string> => {
    try {
      await request('auth/forgot-password', 'POST', { email });
      return true;
    } catch (e: any) {
      return e.message;
    }
  },

  /** Сброс пароля с кодом */
  resetPassword: async (data: any): Promise<boolean> => {
    try {
      await request('auth/reset-password', 'POST', data);
      return true;
    } catch {
      return false;
    }
  },

  /** Боты: получение списка */
  getBots: async (userId: string): Promise<BotConfig[]> => {
    try {
      return await request(`bots/${userId}`);
    } catch (e) { 
      console.warn("Could not fetch bots, returning empty list.");
      return []; 
    }
  },

  /** Боты: сохранение конфигурации */
  saveBot: async (userId: string, bot: BotConfig): Promise<void> => {
    await request('bots/save', 'POST', bot);
  },

  /** Боты: удаление */
  deleteBot: async (userId: string, botId: string): Promise<void> => {
    await request(`bots/delete/${botId}`, 'DELETE');
  },

  /** Боты: запуск процесса на сервере */
  startBotOnServer: async (bot: BotConfig): Promise<boolean | string> => {
    try {
      await request(`bots/start/${bot.id}`, 'POST');
      return true;
    } catch (e: any) {
      return e.message;
    }
  },

  /** Боты: остановка процесса */
  stopBotOnServer: async (botId: string): Promise<boolean> => {
    try {
      await request(`bots/stop/${botId}`, 'POST');
      return true;
    } catch { 
      return false; 
    }
  },

  /** Рассылка */
  sendBroadcast: async (botIds: string[], message: string): Promise<any> => {
    return await request('broadcast', 'POST', { botIds, message });
  },

  /** Лицензии: активация ключа */
  activateLicense: async (botId: string, key: string): Promise<any> => {
    return await request('license/activate', 'POST', { botId, key });
  }
};

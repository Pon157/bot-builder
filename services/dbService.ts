
import { BotConfig } from '../types';

// Версия БД для предотвращения конфликтов со старыми данными
const STORAGE_KEY = 'botengine_cloud_pro_v5';

export const db = {
  saveBots: (bots: BotConfig[]) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bots));
  },
  
  loadAllBots: (): BotConfig[] => {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  },

  loadUserBots: (userId: string): BotConfig[] => {
    const all = db.loadAllBots();
    // Изоляция: возвращаем только ботов текущего пользователя
    return all.filter(b => b.ownerId === userId);
  },

  clearAll: () => {
    localStorage.removeItem(STORAGE_KEY);
  }
};

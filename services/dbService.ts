
import { BotConfig } from '../types';

const STORAGE_KEY = 'botengine_pro_v2_db';

export const db = {
  saveBots: (bots: BotConfig[]) => {
    // Сохраняем всех ботов системы
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bots));
  },
  
  loadAllBots: (): BotConfig[] => {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  },

  loadUserBots: (userId: string): BotConfig[] => {
    const all = db.loadAllBots();
    return all.filter(b => b.ownerId === userId);
  }
};

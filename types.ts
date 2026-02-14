export enum BotStatus {
  IDLE = 'IDLE',
  RUNNING = 'RUNNING',
  ERROR = 'ERROR',
  STARTING = 'STARTING'
}

// Переименовали в BotUser, так как пользователи теперь не только из Telegram
export interface BotUser {
  id: number | string; // В ВК ID может быть строкой или большим числом
  first_name: string;
  last_name?: string;    // Добавили для ВК
  username?: string;     // Для Telegram
  domain?: string;       // Аналог username в ВК
  is_banned: boolean;
  is_active: boolean; 
  joined_at: number;
  last_seen?: number;
  thread_id?: number;    // Только для Telegram (Topics)
  warns: number;
  platform: 'telegram' | 'vk'; // Чтобы отличать юзеров в базе
}

export interface StatPoint {
  date: string;
  incoming: number;
  outgoing: number;
  totalUsers?: number;
  activeUsers?: number;
}

export interface BotStats {
  // Support bot
  totalMessages: number;
  incomingToday: number;
  outgoingToday: number;
  bannedCount: number;
  history: StatPoint[];
  activeUsers24h: number;
  // Poster
  totalPosts?: number;
  // Randomizer
  totalUsers?: number;
  blockedCount?: number;
  totalLotteries?: number;
}

export interface MessageLog {
  id: string;
  timestamp: number;
  type: 'info' | 'error' | 'incoming' | 'outgoing' | 'system';
  text: string;
  code?: string;
}

export interface BotConfig {
  id: string;
  owner_id: string;
  name: string;
  token: string;
  platform: 'telegram' | 'vk' | 'poster' | 'randomizer'; // все 4 типа
  status: BotStatus;
  created_at: number;
  license_expires_at: number;
  usersCount: number;
  description: string;
  adminChatId?: string;
  vkGroupId?: string;
  vk_group_id?: string;
  // Poster / Randomizer fields
  adminIds?: number[];
  channelId?: string;
  lotChannel?: string;
  botLink?: string;
  lotteries?: any[];
  users?: any[];
  welcomeMessage?: string;
  logs?: MessageLog[];
  connectedUsers?: BotUser[]; // Обновили тип здесь
  subscribers?: number[]; 
  triggers?: { keyword: string; response: string }[];
  buttons?: { 
    text: string; 
    response: string; 
    type?: 'message' | 'request';
    // Цвета кнопок для ВК (в ТГ будут игнорироваться)
    color?: 'primary' | 'secondary' | 'negative' | 'positive'; 
    adminTemplate?: string; 
  }[];
  stats?: BotStats;
  config?: any; // raw config from DB
  settings?: {
    useTopics: boolean;
    topicPerRequest: boolean;
    anonymousTopics: boolean;
    forwardToAdmin: boolean;
    antiSpam: boolean;
    showUserInfo: boolean;
    showUsername: boolean;
    autoApproveJoin: boolean;
    rateLimit: number;
    autoBanThreshold: number;
    adminMessageTemplate?: string;
    showHeaderId: boolean;
    showHeaderName: boolean;
    showHeaderUsername: boolean;
    // Настройки для Callback API ВК
    vkConfirmCode?: string;
    vkSecretKey?: string;
  };
}

export interface User {
  id: string;
  username: string;
  email: string;
  password?: string;
  balance: number;
  botsCreated: number;
  license_expires_at: number;
  trialUsed?: boolean;
}

// Алиас для обратной совместимости
export type TelegramUser = BotUser;

// Пользователь рандомайзера (из config.users)
export interface RandomizerUser {
  id: number;
  name: string;
  username?: string;
  joined_at: number;
  is_blocked: boolean;
  participations: number;
  wins: number;
}

// Розыгрыш
export interface Lottery {
  id: number;
  text?: string;
  photo_id?: string | null;
  finish_type: 'time' | 'count';
  finish_value: string;
  winners_count: number;
  status: 'active' | 'finished';
  participants: number[];
  winners: number[];
  message_id?: number | null;
  created_at: string;
  channels?: string;
}

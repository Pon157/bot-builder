export enum BotStatus {
  IDLE = 'IDLE',
  RUNNING = 'RUNNING',
  ERROR = 'ERROR',
  STARTING = 'STARTING'
}

export interface BotUser {
  id: number | string;
  first_name: string;
  last_name?: string;
  username?: string;
  domain?: string;
  is_banned: boolean;
  is_active: boolean; 
  joined_at: number;
  last_seen?: number;
  thread_id?: number;
  warns: number;
  platform: 'telegram' | 'vk';
}

export interface StatPoint {
  date: string;
  incoming: number;
  outgoing: number;
  totalUsers?: number;
  activeUsers?: number;
}

export interface BotStats {
  totalMessages: number;
  incomingToday: number;
  outgoingToday: number;
  bannedCount: number;
  history: StatPoint[];
  activeUsers24h: number;
  totalPosts?: number;
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
  platform: 'telegram' | 'vk' | 'poster' | 'randomizer';
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
  botUsername?: string;  // Username бота для системы защиты DVR
  channelId?: string;
  lotChannel?: string;
  botLink?: string;
  lotteries?: any[];
  users?: any[];
  welcomeMessage?: string;
  logs?: MessageLog[];
  connectedUsers?: BotUser[];
  subscribers?: number[]; 
  triggers?: { keyword: string; response: string }[];
  buttons?: { 
    text: string; 
    response: string; 
    type?: 'message' | 'request';
    color?: 'primary' | 'secondary' | 'negative' | 'positive'; 
    adminTemplate?: string; 
  }[];
  stats?: BotStats;
  config?: any;
  welcomePhoto?: string;
  welcomeInline?: { text: string; url: string }[];
  channels?: string[];
  ai?: {
    mode?: 'off' | 'all' | 'button' | 'command';
    enabled?: boolean;
    model?: string;
    systemPrompt?: string;
    maxTokensPerReply?: number;
    contextMessages?: number;
    buttonName?: string;
  };
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
    notifyOnStart?: boolean;
    notifyOnBlock?: boolean;
    firstMessageHeader?: string;
    ticketMessageHeader?: string;
    commonMessageHeader?: string;
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

export type TelegramUser = BotUser;

export interface RandomizerUser {
  id: number;
  name: string;
  username?: string;
  joined_at: number;
  is_blocked: boolean;
  participations: number;
  wins: number;
}

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

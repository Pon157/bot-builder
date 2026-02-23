import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Send, LogOut, Ban, Megaphone, RefreshCw, MessageCircle, UserPlus,
  ChevronRight, Check, X, Shield, AlertCircle, Image, Smile,
  ArrowLeft, BarChart3, Users, Hash, AtSign, Mail, Eye, EyeOff,
  Paperclip, Play, File as FileIcon, Star, Plus, Mic, MicOff,
  Volume2, VolumeX, Pin, AlertTriangle, Layers, Circle, StopCircle,
  WifiOff, Wifi
} from 'lucide-react';

// ─── Constants ──────────────────────────────────────────────────────────────────

const API = '/api';
const POLL = 2500;

const EMOJI_CATEGORIES = [
  { name: 'Лица', icon: '😊', emojis: ['😀','😃','😄','😁','😆','😅','😂','🤣','😊','😇','🥰','😍','🤩','😘','😙','😚','🙂','🤗','🤔','😐','😑','😏','😒','🙄','😔','😪','😴','😷','🤒','🤕','🤢','🥵','🥶','🥴','😵','🤯','🥳','😎','😕','😟','🙁','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','😤','😡','😠','🤬','😈','💀','👻','👾','🤖','💩','🤡'] },
  { name: 'Жесты', icon: '👋', emojis: ['👋','🤚','🖐','✋','🖖','👌','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','👇','☝️','👍','👎','✊','👊','🤛','🤜','👏','🙌','👐','🤲','🤝','🙏','💪','👀','👄','💋','❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💯','💢','💥','💫','✨','🔥','💧','💦','⚡'] },
  { name: 'Животные', icon: '🐶', emojis: ['🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🐔','🐧','🐦','🦆','🦅','🦉','🐺','🐴','🦄','🐝','🦋','🐢','🐍','🦎','🐙','🦑','🦐','🦀','🐡','🐠','🐟','🐬','🐳','🦈','🐘','🦒','🦘','🐄','🐑','🐈','🦁','🐾'] },
  { name: 'Еда', icon: '🍕', emojis: ['🍏','🍎','🍊','🍋','🍌','🍉','🍇','🍓','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🥑','🥦','🌽','🍄','🍞','🥐','🧀','🥚','🍳','🥞','🍗','🍖','🌭','🍔','🍟','🍕','🥪','🌮','🌯','🍝','🍜','🍣','🍱','🍤','🍙','🍚','🧁','🍰','🎂','🍭','🍬','🍫','🍿','🍩','🍪','☕','🍵','🍺','🍻','🥂','🍷','🍸','🍹','🍾'] },
  { name: 'Объекты', icon: '💡', emojis: ['🎁','🎀','🎊','🎉','🎈','💌','📱','💻','📷','📹','📞','📺','💡','🔦','💰','💎','👑','🎒','🛡️','🔑','🔨','🔧','🔫','🔭','🔬','💊','📝','✏️','📏','✂️','🔒','🔓','🔔','🎵','🎶','🎹','🎸','🎺','🥁','🎮','🎲','🎯','🎱','⚽','🏀','🏈','⚾','🎾','🏐','🎿','🛷'] },
  { name: 'Символы', icon: '❤️', emojis: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💟','☮️','✝️','☪️','🕉️','☯️','✅','❌','⭕','🛑','⛔','📛','🚫','💯','❗','❕','❓','❔','‼️','⁉️','✔️','🔀','🔁','🔂','▶️','⏩','⏭️','◀️','⏪','⏮️'] },
];

const STICKER_PACKS = [
  { name: 'Реакции', stickers: ['😂','🤣','😭','😍','🥰','🤩','😤','🤯','🥳','🎉','💪','👏','🙌','✨','💥','🔥','❤️','💔','😘','🫶','💯','🤦','🤷','🙆','🙅','💁','🫠','😮‍💨'] },
  { name: 'Поддержка', stickers: ['💪','🤝','🫂','🙏','❤️','🫶','🌟','⭐','✨','🎯','🏆','🥇','👑','🌈','🎊','🎉','🎈','💐','🌸','🌺'] },
  { name: 'Грусть/Радость', stickers: ['😢','😭','😿','💧','😊','😁','😄','🎊','🎉','🥳','🤗','😂','🤣','😅','😌','😔','😞','😟','😤','😡'] },
  { name: 'Коты', stickers: ['😺','😸','😹','😻','😼','😽','🙀','😿','😾','🐱','🐈','🐈‍⬛','🐾','🦁','🐯','🦊','🦝','🐻','🐻‍❄️','🐨'] },
];

// ─── Types ──────────────────────────────────────────────────────────────────────

interface SiteConfig {
  primaryColor: string; bgColor: string; fontFamily: string;
  welcomeMessage: string; commands: string[]; logoText: string;
  requireEmailVerification?: boolean; showOnlineStatus?: boolean;
  borderRadius?: string;
  fontScale?: string;
  autoReplies?: { command: string; reply: string }[];
  groupChatEnabled?: boolean;
  maxWarnsBeforeBan?: number;
  theme?: 'dark' | 'light'; // светлая/тёмная тема
}

interface PublicSite { id: string; name: string; slug: string; config: SiteConfig; }

interface ChatSession {
  id: string; username: string; display_name: string;
  site_id: string; role: 'user' | 'admin' | 'owner';
  avatar_color?: string; token: string;
}

interface AdminInfo {
  id: string; display_name: string; bio: string;
  avatar_color: string; is_online: boolean;
}

interface Conversation {
  id: string; site_id: string; user_id: string; admin_id: string;
  user_name: string; admin_name: string;
  last_message_at: number; last_message_preview: string;
  unread_admin: number; unread_user: number;
}

interface Message {
  id: string; conversation_id: string; site_id?: string; from_id: string; from_name: string;
  from_role: 'user' | 'admin' | 'owner' | 'system';
  text: string | null; media_url: string | null;
  media_type: 'image' | 'video' | 'audio' | 'file' | 'sticker' | null;
  sticker_emoji: string | null; created_at: number; is_read: boolean;
  is_pinned?: boolean; pinned_by?: string;
  duration?: number | null; is_deleted?: boolean;
}

interface GroupMessage {
  id: string; site_id: string; from_id: string; from_name: string;
  from_role: 'user' | 'admin' | 'owner' | 'system';
  text: string | null; media_url: string | null;
  media_type: string | null; sticker_emoji: string | null;
  is_pinned: boolean; pinned_by: string | null;
  created_at: number; is_deleted: boolean;
}

interface SiteUser {
  id: string; username: string; email: string | null;
  is_banned: boolean; ban_reason: string | null;
  muted_until: number; warn_count: number;
  last_seen: number; created_at: number;
}

// ─── CSS radius helper ──────────────────────────────────────────────────────────
const getRadius = (cfg?: SiteConfig) => {
  const map: Record<string,string> = {
    none: '4px', md: '8px', xl: '14px', '2xl': '20px', full: '999px'
  };
  return map[cfg?.borderRadius || '2xl'] || '20px';
};

const getBubbleRadius = (isOwn: boolean, cfg?: SiteConfig) => {
  const r = getRadius(cfg);
  if (cfg?.borderRadius === 'none') return r;
  if (cfg?.borderRadius === 'full') return isOwn ? '20px 20px 4px 20px' : '20px 20px 20px 4px';
  return isOwn ? `${r} ${r} 4px ${r}` : `${r} ${r} ${r} 4px`;
};

const getFontSize = (cfg?: SiteConfig) => {
  const map: Record<string,string> = { sm: '13px', md: '14px', lg: '16px' };
  return map[cfg?.fontScale || 'md'] || '14px';
};

// ─── Theme helpers ───────────────────────────────────────────────────────────────
const isLight = (cfg?: SiteConfig) => cfg?.theme === 'light';

// Returns theme-aware colors
const themeVars = (cfg?: SiteConfig) => {
  const light = isLight(cfg);
  return {
    bg: light ? (cfg?.bgColor || '#f8f9fa') : (cfg?.bgColor || '#09090b'),
    surface: light ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.06)',
    surface2: light ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.04)',
    border: light ? 'rgba(0,0,0,0.10)' : 'rgba(255,255,255,0.08)',
    text: light ? '#111111' : '#ffffff',
    textMuted: light ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.35)',
    textFaint: light ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.20)',
    inputBg: light ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.06)',
    msgOwn: cfg?.primaryColor || '#6366f1',       // sender bubble: always primary
    msgOther: light ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)',
    msgAdmin: light
      ? ((cfg?.primaryColor || '#6366f1') + '18')
      : ((cfg?.primaryColor || '#6366f1') + '18'),
    msgOwnText: '#ffffff',
    msgOtherText: light ? '#111111' : '#ffffff',
    scrollbar: light ? '#00000015' : '#ffffff15',
  };
};

// ─── Helpers ────────────────────────────────────────────────────────────────────

const fmtTime = (ts: number) => new Date(ts).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
const fmtDate = (ts: number) => {
  const d = new Date(ts), n = new Date();
  if (d.toDateString() === n.toDateString()) return 'Сегодня';
  const yesterday = new Date(n); yesterday.setDate(n.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return 'Вчера';
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'long' });
};

async function apiFetch(url: string, opts: RequestInit = {}) {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json', ...((opts as any).headers || {}) }, ...opts });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Ошибка сервера'); }
  return r.json();
}

// ─── Avatar ─────────────────────────────────────────────────────────────────────

const Avatar: React.FC<{ name: string; color?: string; size?: string; online?: boolean }> = ({
  name, color = '#6366f1', size = 'w-8 h-8', online
}) => (
  <div className={`${size} rounded-full flex items-center justify-center font-black text-white text-xs relative shrink-0`}
    style={{ background: color + '40', border: `1.5px solid ${color}60` }}>
    {name[0]?.toUpperCase()}
    {online !== undefined && (
      <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-black ${online ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
    )}
  </div>
);

// ─── Emoji Picker ───────────────────────────────────────────────────────────────

const EmojiPicker: React.FC<{ onSelect: (e: string) => void; primary: string }> = ({ onSelect, primary }) => {
  const [cat, setCat] = useState(0);
  return (
    <div className="bg-[#111] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden w-64 sm:w-72">
      <div className="flex border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {EMOJI_CATEGORIES.map((c, i) => (
          <button key={i} onClick={() => setCat(i)}
            className="p-2.5 text-base shrink-0 transition-all"
            style={{ background: cat === i ? primary + '20' : 'transparent', opacity: cat === i ? 1 : 0.5 }}>
            {c.icon}
          </button>
        ))}
      </div>
      <div className="p-2 grid grid-cols-7 sm:grid-cols-8 gap-0.5 max-h-44 overflow-y-auto no-scrollbar">
        {EMOJI_CATEGORIES[cat].emojis.map(e => (
          <button key={e} onClick={() => onSelect(e)}
            className="w-7 h-7 flex items-center justify-center text-lg hover:bg-white/10 rounded-lg transition-all hover:scale-125">
            {e}
          </button>
        ))}
      </div>
    </div>
  );
};

// ─── Sticker Picker ─────────────────────────────────────────────────────────────

const StickerPicker: React.FC<{ onSelect: (s: string) => void; primary: string }> = ({ onSelect, primary }) => {
  const [pack, setPack] = useState(0);
  return (
    <div className="bg-[#111] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden w-64 sm:w-72">
      <div className="flex border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {STICKER_PACKS.map((p, i) => (
          <button key={i} onClick={() => setPack(i)}
            className="px-2 sm:px-3 py-2 text-[9px] font-black uppercase tracking-wider shrink-0 transition-all whitespace-nowrap"
            style={{ color: pack === i ? primary : 'rgba(255,255,255,0.3)', borderBottom: `2px solid ${pack === i ? primary : 'transparent'}` }}>
            {p.name}
          </button>
        ))}
      </div>
      <div className="p-3 grid grid-cols-5 gap-2 max-h-48 overflow-y-auto no-scrollbar">
        {STICKER_PACKS[pack].stickers.map((s, i) => (
          <button key={i} onClick={() => onSelect(s)}
            className="w-11 h-11 sm:w-12 sm:h-12 flex items-center justify-center text-3xl hover:bg-white/10 rounded-xl transition-all hover:scale-125">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
};

// ─── Message Bubble ─────────────────────────────────────────────────────────────

const MessageBubble: React.FC<{
  msg: Message | GroupMessage; session: ChatSession; primary: string; cfg?: SiteConfig;
  isAdmin?: boolean; onPin?: (id: string, pin: boolean) => void;
}> = ({ msg, session, primary, cfg, onPin }) => {
  const isOwn = msg.from_id === session.id;
  const isSystem = msg.from_role === 'system';
  const isAdminMsg = msg.from_role === 'admin' || msg.from_role === 'owner';
  const canPin = (session.role === 'admin' || session.role === 'owner') && onPin;
  const bubbleRadius = getBubbleRadius(isOwn, cfg);
  const fontSize = getFontSize(cfg);

  if (isSystem) {
    return (
      <div className="flex justify-center my-3">
        <div className="flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-bold"
          style={{ background: primary + '15', color: primary + 'aa' }}>
          <Megaphone className="w-3 h-3" />
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.media_type === 'sticker' && msg.sticker_emoji) {
    return (
      <div className={`flex gap-2 mb-2 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
        {!isOwn && <Avatar name={msg.from_name} color={isAdminMsg ? primary : '#71717a'} />}
        <div className="flex flex-col gap-1" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
          {!isOwn && <span className="text-[9px] font-black uppercase px-1" style={{ color: isAdminMsg ? primary : themeVars(cfg).textMuted }}>{msg.from_name}</span>}
          <div className="text-5xl sm:text-6xl leading-none">{msg.sticker_emoji}</div>
          <span className="text-[9px] px-1" style={{ color: themeVars(cfg).textFaint }}>{fmtTime(msg.created_at)}</span>
        </div>
      </div>
    );
  }

  if (msg.media_url && String(msg.media_url).trim()) {
    // Определяем тип медиа по URL если не указан
    const rawUrl = msg.media_url;
    const absUrl = rawUrl.startsWith('http') ? rawUrl : window.location.origin + rawUrl;
    const ext = rawUrl.split('.').pop()?.toLowerCase().split('?')[0] || '';
    const detectedType: string = msg.media_type || (
      ['jpg','jpeg','png','gif','webp','svg'].includes(ext) ? 'image' :
      ['mp4','webm','mov','avi'].includes(ext) ? 'video' :
      ['mp3','ogg','wav','webm','m4a'].includes(ext) ? 'audio' : 'file'
    );
    return (
      <div className={`flex gap-2 mb-2 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
        {!isOwn && <Avatar name={msg.from_name} color={isAdminMsg ? primary : '#71717a'} />}
        <div className="flex flex-col gap-1 max-w-[80%] sm:max-w-[65%]" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
          {!isOwn && <span className="text-[9px] font-black uppercase px-1" style={{ color: isAdminMsg ? primary : themeVars(cfg).textMuted }}>{msg.from_name}</span>}
          
          {'is_pinned' in msg && msg.is_pinned && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-lg text-[8px] font-bold" style={{ background: primary + '20', color: primary }}>
              <Pin className="w-2.5 h-2.5" /> Закреплено
            </div>
          )}
          
          <div className="rounded-2xl overflow-hidden border" style={{ borderColor: primary + '20' }}>
            {detectedType === 'image' && (
              <div className="relative">
                <img
                  src={absUrl}
                  alt="img"
                  className="max-w-[200px] sm:max-w-xs max-h-64 object-cover cursor-pointer block"
                  loading="lazy"
                  onError={(e) => {
                    const t = e.currentTarget;
                    t.style.display = 'none';
                    const p = t.parentElement;
                    if (p && !p.querySelector('.img-err')) {
                      const d = document.createElement('div');
                      d.className = 'img-err flex items-center gap-2 px-4 py-3 text-xs';
                      d.style.color = themeVars(cfg).textMuted;
                      d.textContent = '🖼 Изображение не загрузилось';
                      p.appendChild(d);
                    }
                  }}
                  onClick={() => window.open(absUrl, '_blank', 'noopener,noreferrer')}
                />
              </div>
            )}
            {detectedType === 'video' && (
              <video src={absUrl} controls className="max-w-[200px] sm:max-w-xs max-h-64" />
            )}
            {detectedType === 'audio' && (
              <div className="flex items-center gap-2 px-3 py-3 min-w-[180px]" style={{ background: themeVars(cfg).surface }}>
                <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0" style={{ background: primary + '30' }}>
                  <Volume2 className="w-4 h-4" style={{ color: primary }} />
                </div>
                <div className="flex flex-col gap-0.5 flex-1">
                  <audio src={absUrl} controls className="w-full h-8" style={{ accentColor: primary }} preload="metadata" />
                  {(msg as any).duration > 0 && (
                    <span className="text-[9px]" style={{ color: themeVars(cfg).textMuted }}>{`${Math.floor((msg as any).duration / 60)}:${String((msg as any).duration % 60).padStart(2,'0')}`}</span>
                  )}
                </div>
              </div>
            )}
            {detectedType === 'file' && (
              <a
                href={absUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-4 py-3 transition-all min-w-[160px]"
                style={{ background: themeVars(cfg).surface }}
                onMouseEnter={e => (e.currentTarget.style.background = themeVars(cfg).surface2)}
                onMouseLeave={e => (e.currentTarget.style.background = themeVars(cfg).surface)}
                onClick={e => {
                  e.preventDefault();
                  const a = document.createElement('a');
                  a.href = absUrl;
                  a.download = rawUrl.split('/').pop() || 'file';
                  document.body.appendChild(a); a.click(); document.body.removeChild(a);
                }}
              >
                <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0" style={{ background: primary + '20' }}>
                  <FileIcon className="w-4 h-4" style={{ color: primary }} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold truncate max-w-[140px]" style={{ color: themeVars(cfg).text }}>
                    {rawUrl.split('/').pop()?.replace(/^\d+_\d+_/, '') || 'Файл'}
                  </p>
                  <p className="text-[9px]" style={{ color: themeVars(cfg).textMuted }}>Скачать</p>
                </div>
              </a>
            )}
          </div>
          {msg.text && (
            <div className="px-3 py-2.5 text-sm" style={{ background: isOwn ? primary : themeVars(cfg).surface, color: isOwn ? '#fff' : themeVars(cfg).text, borderRadius: bubbleRadius }}>
              {msg.text}
            </div>
          )}
          <div className="flex items-center gap-2 px-1">
            <span className="text-[9px]" style={{ color: themeVars(cfg).textFaint }}>{fmtTime(msg.created_at)}</span>
            {canPin && (
              <button onClick={() => onPin!(msg.id, !('is_pinned' in msg && msg.is_pinned))}
                className="opacity-0 group-hover:opacity-100 transition-opacity">
                <Pin className="w-2.5 h-2.5" style={{ color: themeVars(cfg).textMuted }} />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-2 mb-2 group ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isOwn && <Avatar name={msg.from_name} color={isAdminMsg ? primary : '#71717a'} />}
      <div className="flex flex-col gap-1 max-w-[85%] sm:max-w-[72%]" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
        {!isOwn && (
          <span className="text-[9px] font-black uppercase tracking-wider px-1"
            style={{ color: isAdminMsg ? primary : themeVars(cfg).textMuted }}>
            {msg.from_name}
          </span>
        )}
        {'is_pinned' in msg && msg.is_pinned && (
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-lg text-[8px] font-bold" style={{ background: primary + '20', color: primary }}>
            <Pin className="w-2.5 h-2.5" /> Закреплено
          </div>
        )}
        <div className="relative">
          <div className="px-3 sm:px-4 py-2.5 sm:py-3 leading-relaxed whitespace-pre-wrap break-words"
            style={{
              background: isOwn ? primary : isAdminMsg ? primary + '18' : themeVars(cfg).msgOther,
              color: isOwn ? '#fff' : themeVars(cfg).msgOtherText,
              borderRadius: bubbleRadius,
              fontSize,
            }}>
            {msg.text}
          </div>
          {canPin && (
            <button onClick={() => onPin!(msg.id, !('is_pinned' in msg && msg.is_pinned))}
              className="absolute -top-2 right-0 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg"
              style={{ background: themeVars(cfg).surface2 }}>
              <Pin className="w-2.5 h-2.5" style={{ color: themeVars(cfg).textMuted }} />
            </button>
          )}
        </div>
        <span className="text-[9px] px-1 flex items-center gap-1" style={{ color: themeVars(cfg).textFaint }}>
          {fmtTime(msg.created_at)}
          {isOwn && <Check className="w-2.5 h-2.5" />}
        </span>
      </div>
    </div>
  );
};

// ─── Voice Recorder ─────────────────────────────────────────────────────────────

const VoiceRecorder: React.FC<{
  onRecorded: (blob: Blob, duration: number) => void;
  primary: string; cfg?: SiteConfig;
}> = ({ onRecorded, primary, cfg }) => {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout>();
  const startTimeRef = useRef<number>(0);

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Выбираем поддерживаемый формат
      const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/mpeg'];
      const supportedMime = mimeTypes.find(t => MediaRecorder.isTypeSupported(t)) || '';
      const mr = new MediaRecorder(stream, supportedMime ? { mimeType: supportedMime } : {});
      const ext = supportedMime.includes('ogg') ? 'ogg' : supportedMime.includes('mp4') ? 'mp4' : 'webm';
      chunksRef.current = [];
      (mr as any)._ext = ext;
      (mr as any)._mime = mr.mimeType || 'audio/webm';
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      const recordingStarted = Date.now();  // closure var — 100% accurate
      mr.onstop = () => {
        const durationMs = Date.now() - recordingStarted;
        const durationSec = Math.max(1, Math.round(durationMs / 1000));
        const finalMime = (mr as any)._mime || 'audio/webm';
        const finalExt = (mr as any)._ext || 'webm';
        const blob = new Blob(chunksRef.current, { type: finalMime });
        (blob as any)._ext = finalExt;
        onRecorded(blob, durationSec);
        stream.getTracks().forEach(t => t.stop());
      };
      startTimeRef.current = Date.now();  // ← MUST be before start()
      mr.start(100);
      mediaRef.current = mr;
      setRecording(true);
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds(s => s + 1), 1000);
    } catch {
      alert('Нет доступа к микрофону');
    }
  };

  const stop = () => {
    if (mediaRef.current && mediaRef.current.state === 'recording') {
      mediaRef.current.requestData();  // flush remaining chunks
    }
    mediaRef.current?.stop();
    clearInterval(timerRef.current);
    setRecording(false);
    setSeconds(0);
  };

  const cancel = () => {
    if (mediaRef.current?.state === 'recording') {
      mediaRef.current.ondataavailable = null;
      mediaRef.current.onstop = null;
      mediaRef.current.stop();
      mediaRef.current.stream?.getTracks().forEach(t => t.stop());
    }
    clearInterval(timerRef.current);
    setRecording(false);
    setSeconds(0);
  };

  if (recording) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl animate-pulse" style={{ background: primary + '15' }}>
        <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
        <span className="text-xs font-mono" style={{ color: themeVars(cfg).text }}>{String(Math.floor(seconds / 60)).padStart(2,'0')}:{String(seconds % 60).padStart(2,'0')}</span>
        <button onClick={cancel} className="p-1 rounded-lg transition-all" style={{ background: themeVars(cfg).surface }}>
          <X className="w-3.5 h-3.5" style={{ color: themeVars(cfg).textMuted }} />
        </button>
        <button onClick={stop}
          className="w-8 h-8 rounded-full flex items-center justify-center"
          style={{ background: primary }}>
          <Check className="w-4 h-4 text-white" />
        </button>
      </div>
    );
  }

  return (
    <button onClick={start}
      className="w-9 h-9 rounded-xl flex items-center justify-center transition-all"
      style={{ background: themeVars(cfg).surface, color: themeVars(cfg).textMuted }}>
      <Mic className="w-4 h-4" />
    </button>
  );
};

// ─── Message Input ──────────────────────────────────────────────────────────────

const MessageInput: React.FC<{
  onSend: (text: string, mediaUrl?: string, mediaType?: string, sticker?: string, duration?: number) => Promise<void>;
  primary: string; commands: string[]; placeholder?: string; cfg?: SiteConfig;
}> = ({ onSend, primary, commands, placeholder = 'Напишите сообщение...', cfg }) => {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showStickers, setShowStickers] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const pickersRef = useRef<HTMLDivElement>(null);

  const filteredCmds = text.startsWith('/') ? commands.filter(c => c.startsWith(text)) : [];

  const doSend = async () => {
    const t = text.trim();
    if (!t || sending) return;
    setSending(true);
    setText('');
    setShowEmoji(false);
    setShowStickers(false);
    try { await onSend(t); } catch { setText(t); }
    finally { setSending(false); inputRef.current?.focus(); }
  };

  const doSticker = async (s: string) => {
    setShowStickers(false);
    setSending(true);
    try { await onSend('', undefined, undefined, s); } catch { }
    finally { setSending(false); }
  };

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch(`${API}/chat/media/upload`, { method: 'POST', body: fd });
      if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail || 'Ошибка загрузки'); }
      const { url, media_type } = await r.json();
      await onSend(text.trim() || '', url, media_type);
      setText('');
    } catch (e: any) { alert(e.message || 'Ошибка загрузки файла'); }
    finally { setUploading(false); }
  };

  const handleVoice = async (blob: Blob, duration?: number) => {
    setUploading(true);
    try {
      const fd = new FormData();
      const blobExt = (blob as any)._ext || 'webm';
      const blobMime = blob.type || 'audio/webm';
      fd.append('file', new File([blob], `voice_${Date.now()}.${blobExt}`, { type: blobMime }));
      fd.append('is_voice', 'true');
      const r = await fetch(`${API}/chat/media/upload`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('Ошибка загрузки голосового');
      const { url } = await r.json();
      await onSend('', url, 'audio', undefined, duration || 1);
    } catch (e: any) { alert(e.message || 'Ошибка'); }
    finally { setUploading(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
    if (e.key === 'Escape') { setShowEmoji(false); setShowStickers(false); setShowCommands(false); }
  };

  const r = getRadius(cfg);
  const tv = themeVars(cfg);

  return (
    <div className="relative">
      {/* Команды-подсказки */}
      {showCommands && filteredCmds.length > 0 && (
        <div className="absolute bottom-full mb-1 left-0 right-0 border rounded-2xl overflow-hidden shadow-xl z-10"
          style={{ background: tv.bg, borderColor: tv.border }}>
          {filteredCmds.map(cmd => (
            <button key={cmd} onClick={() => { setText(cmd + ' '); setShowCommands(false); inputRef.current?.focus(); }}
              className="flex items-center gap-2 w-full px-4 py-2.5 transition-colors text-left text-xs"
              style={{ color: tv.text }}
              onMouseEnter={e => (e.currentTarget.style.background = tv.surface)}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
              <Hash className="w-3 h-3" style={{ color: primary }} />
              <span className="font-mono">{cmd}</span>
            </button>
          ))}
        </div>
      )}

      {/* Emoji / Sticker picker */}
      {(showEmoji || showStickers) && (
        <div ref={pickersRef} className="absolute bottom-full mb-2 left-0 z-20">
          {showEmoji && <EmojiPicker onSelect={e => { setText(t => t + e); setShowEmoji(false); inputRef.current?.focus(); }} primary={primary} />}
          {showStickers && <StickerPicker onSelect={doSticker} primary={primary} />}
        </div>
      )}

      {/* Upload input */}
      <input ref={fileRef} type="file" className="hidden" accept="*/*"
        onChange={e => { const f = e.target.files?.[0]; if (f) { handleFile(f); e.target.value = ''; } }} />

      <div className="flex gap-1.5 sm:gap-2 items-end p-2 sm:p-3 border-t" style={{ borderColor: primary + '15', background: tv.bg }}>
        <div className="flex gap-1 shrink-0">
          <button onClick={() => { setShowEmoji(v => !v); setShowStickers(false); }}
            className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl flex items-center justify-center transition-all text-base sm:text-lg"
            style={{ background: showEmoji ? primary + '30' : tv.surface }}>
            😊
          </button>
          <button onClick={() => { setShowStickers(v => !v); setShowEmoji(false); }}
            className="hidden sm:flex w-9 h-9 rounded-xl items-center justify-center transition-all text-lg"
            style={{ background: showStickers ? primary + '30' : tv.surface }}>
            🌟
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={uploading}
            className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl flex items-center justify-center transition-all disabled:opacity-40"
            style={{ background: tv.surface, color: tv.textMuted }}>
            {uploading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Paperclip className="w-3.5 h-3.5 sm:w-4 sm:h-4" />}
          </button>
          {!text.trim() && (
            <VoiceRecorder onRecorded={handleVoice} primary={primary} cfg={cfg} />
          )}
        </div>

        <textarea
          ref={inputRef}
          value={text}
          onChange={e => { setText(e.target.value); setShowCommands(e.target.value.startsWith('/')); }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="flex-1 px-3 sm:px-4 py-2 sm:py-2.5 text-sm outline-none resize-none overflow-hidden leading-relaxed"
          style={{
            background: tv.surface,
            border: `1.5px solid ${primary}25`,
            borderRadius: r,
            maxHeight: '120px',
            caretColor: primary,
            fontSize: getFontSize(cfg),
            color: tv.text,
          }}
          onInput={e => { const el = e.target as HTMLTextAreaElement; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }}
        />

        <button onClick={doSend} disabled={!text.trim() || sending}
          className="w-9 h-9 sm:w-10 sm:h-10 flex items-center justify-center transition-all disabled:opacity-30 shrink-0"
          style={{ background: primary, borderRadius: r, boxShadow: `0 4px 14px ${primary}50` }}>
          {sending ? <RefreshCw className="w-4 h-4 text-white animate-spin" /> : <Send className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-white" />}
        </button>
      </div>
    </div>
  );
};

// ─── Group Chat ─────────────────────────────────────────────────────────────────

const GroupChat: React.FC<{ site: PublicSite; session: ChatSession }> = ({ site, session }) => {
  const [messages, setMessages] = useState<GroupMessage[]>([]);
  const [pinned, setPinned] = useState<GroupMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPinned, setShowPinned] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const p = site.config.primaryColor || '#6366f1';

  const loadMessages = useCallback(async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/group?limit=100`);
      setMessages(Array.isArray(data) ? data : []);
    } catch { } finally { setLoading(false); }
  }, [site.slug]);

  const loadPinned = async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/group/pinned`);
      setPinned(Array.isArray(data) ? data : []);
    } catch { }
  };

  useEffect(() => {
    loadMessages();
    loadPinned();
    const interval = setInterval(loadMessages, POLL);
    return () => clearInterval(interval);
  }, [loadMessages]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length]);

  const handleSend = async (text: string, mediaUrl?: string, mediaType?: string, sticker?: string, duration?: number) => {
    await apiFetch(`${API}/chat/site/${site.slug}/group`, {
      method: 'POST',
      body: JSON.stringify({
        from_id: session.id, 
        from_name: session.display_name || session.username || "Пользователь",
        from_role: session.role, 
        text: text || null,
        media_url: mediaUrl, 
        media_type: mediaType,
        sticker_emoji: sticker,
        duration: duration || null
      })
    });
    await loadMessages();
  };

  const handlePin = async (msgId: string, pin: boolean) => {
    await apiFetch(`${API}/chat/site/${site.slug}/group/${msgId}/pin`, {
      method: 'POST',
      body: JSON.stringify({ role: session.role, pin, pinned_by: session.display_name })
    });
    await loadMessages();
    await loadPinned();
  };

  const handleDelete = async (msgId: string) => {
    if (session.role !== 'admin' && session.role !== 'owner') return;
    await fetch(`${API}/chat/site/${site.slug}/group/${msgId}?role=${session.role}`, { method: 'DELETE' });
    setMessages(prev => prev.filter(m => m.id !== msgId));
  };

  // Group by date
  const grouped: { date: string; msgs: GroupMessage[] }[] = [];
  for (const msg of messages) {
    const d = fmtDate(msg.created_at);
    if (!grouped.length || grouped[grouped.length-1].date !== d) grouped.push({ date: d, msgs: [] });
    grouped[grouped.length-1].msgs.push(msg);
  }

  return (
    <div className="flex flex-col h-full" style={{ fontFamily: site.config.fontFamily || 'Manrope, sans-serif' }}>
      {/* Pinned messages bar */}
      {pinned.length > 0 && (
        <div className="px-4 py-2 border-b cursor-pointer transition-all shrink-0"
          style={{ borderColor: p + '20' }}
          onMouseEnter={e => e.currentTarget.style.background = themeVars(site.config).surface}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          onClick={() => setShowPinned(v => !v)}>
          <div className="flex items-center gap-2">
            <Pin className="w-3.5 h-3.5" style={{ color: p }} />
            <span className="text-[10px] font-black uppercase tracking-widest" style={{ color: p }}>
              {pinned.length} закреплённых
            </span>
            <ChevronRight className={`w-3 h-3 ml-auto transition-transform ${showPinned ? 'rotate-90' : ''}`} style={{ color: themeVars(site.config).textFaint }} />
          </div>
          {showPinned && (
            <div className="mt-2 space-y-1.5 max-h-32 overflow-y-auto">
              {pinned.map(m => (
                <div key={m.id} className="px-3 py-2 rounded-xl text-xs border" style={{ background: p + '08', borderColor: p + '20', color: themeVars(site.config).text }}>
                  <span className="font-black text-[9px] uppercase" style={{ color: p }}>{m.from_name}: </span>
                  {m.text || (m.media_type === 'image' ? '🖼 Изображение' : '📎 Файл')}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-0.5">
        {loading ? (
          <div className="flex justify-center py-8"><RefreshCw className="w-5 h-5 animate-spin" style={{ color: themeVars(site.config).textFaint }} /></div>
        ) : messages.length === 0 ? (
          <div className="text-center py-16">
            <MessageCircle className="w-10 h-10 mx-auto mb-3" style={{ color: p + '30' }} />
            <p className="font-bold text-sm" style={{ color: themeVars(site.config).textMuted }}>Групповой чат пуст</p>
            <p className="text-xs mt-1" style={{ color: themeVars(site.config).textFaint }}>Напишите первым!</p>
          </div>
        ) : grouped.map(({ date, msgs }) => (
          <div key={date}>
            <div className="flex justify-center my-4">
              <span className="text-[10px] font-bold px-3 py-1 rounded-full" style={{ background: p + '15', color: p + 'aa' }}>{date}</span>
            </div>
            {msgs.map(msg => (
              <div key={msg.id} className="group relative">
                <MessageBubble msg={msg} session={session} primary={p} cfg={site.config}
                  onPin={(session.role === 'admin' || session.role === 'owner') ? handlePin : undefined} />
                {(session.role === 'admin' || session.role === 'owner') && !msg.is_deleted && (
                  <button onClick={() => handleDelete(msg.id)}
                    className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 p-1 rounded-lg bg-rose-500/20 text-rose-400 transition-all text-[9px]">
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <MessageInput onSend={handleSend} primary={p} commands={site.config.commands || []} placeholder="Написать в чат..." cfg={site.config} />
    </div>
  );
};

// ─── Auth Screen ─────────────────────────────────────────────────────────────────

const AuthScreen: React.FC<{ site: PublicSite; forceAdmin?: boolean; onAuth: (s: ChatSession) => void }> = ({ site, forceAdmin, onAuth }) => {
  const cfg = site.config;
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [verifyCode, setVerifyCode] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState('');

  const p = cfg.primaryColor || '#6366f1';
  const font = cfg.fontFamily || 'Manrope, sans-serif';
  const r = getRadius(cfg);
  const tv = themeVars(cfg);
  const bg = tv.bg;

  const sendCode = async () => {
    if (!email || !email.includes('@')) { setError('Введите корректный email'); return; }
    setLoading(true); setError('');
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/verify-email`, { method: 'POST', body: JSON.stringify({ email }) });
      setCodeSent(true);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleSubmit = async () => {
    if (!login.trim() || !password.trim()) { setError('Заполните все поля'); return; }
    setLoading(true); setError('');
    try {
      if (mode === 'register') {
        const body: any = { username: login.trim(), password: password.trim() };
        if (email) body.email = email;
        if (verifyCode) body.verify_code = verifyCode;
        const data = await apiFetch(`${API}/chat/site/${site.slug}/register`, { method: 'POST', body: JSON.stringify(body) });
        onAuth(data);
      } else {
        const data = await apiFetch(`${API}/chat/site/${site.slug}/auth`, {
          method: 'POST', body: JSON.stringify({ login: login.trim(), password: password.trim() })
        });
        onAuth(data);
      }
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4" style={{ background: bg, fontFamily: font }}>
      <div className="mb-8 text-center">
        <div className="inline-flex items-center gap-3 mb-2">
          <div className="w-3.5 h-3.5 rounded-full" style={{ background: p }} />
          <span className="text-2xl sm:text-3xl font-black" style={{ color: p }}>{cfg.logoText || site.name}</span>
        </div>
        {!forceAdmin && <p className="text-sm mt-1" style={{ color: p + '90' }}>{cfg.welcomeMessage || 'Чем можем помочь?'}</p>}
        {forceAdmin && <p className="text-xs mt-1 font-bold uppercase tracking-widest" style={{ color: p + '70' }}>Панель администратора</p>}
      </div>

      <div className="w-full max-w-sm rounded-[2rem] p-6 sm:p-8 backdrop-blur-sm" style={{ background: tv.surface, border: `1px solid ${p}25` }}>
        {!forceAdmin && (
          <div className="flex rounded-2xl overflow-hidden border mb-5" style={{ borderColor: p + '25' }}>
            {(['login', 'register'] as const).map(m => (
              <button key={m} onClick={() => { setMode(m); setError(''); }}
                className="flex-1 py-3 text-[10px] font-black uppercase tracking-widest transition-all"
                style={{ background: mode === m ? p : 'transparent', color: mode === m ? '#fff' : p + '80' }}>
                {m === 'login' ? 'Войти' : 'Регистрация'}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: tv.textMuted }}>
              {mode === 'register' ? 'Имя пользователя' : 'Логин'}
            </label>
            <input value={login} onChange={e => setLogin(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder={mode === 'register' ? 'Никнейм' : 'Введите логин'} autoFocus
              className="w-full border text-sm p-3.5 outline-none transition-all"
              style={{ background: tv.inputBg, borderColor: p + '30', borderRadius: r, color: tv.text }} />
          </div>

          {mode === 'register' && (
            <div>
              <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: tv.textMuted }}>Email (опционально)</label>
              <div className="flex gap-2">
                <input value={email} onChange={e => setEmail(e.target.value)} type="email" placeholder="you@example.com"
                  className="flex-1 border text-sm p-3.5 outline-none transition-all"
                  style={{ background: tv.inputBg, borderColor: p + '30', borderRadius: r, color: tv.text }} />
                {cfg.requireEmailVerification && (
                  <button onClick={sendCode} disabled={loading || codeSent}
                    className="px-3 py-2 text-[9px] font-black uppercase tracking-wider disabled:opacity-40 whitespace-nowrap transition-all"
                    style={{ background: p + '20', color: p, border: `1px solid ${p}30`, borderRadius: r }}>
                    {codeSent ? '✓' : 'Код'}
                  </button>
                )}
              </div>
            </div>
          )}

          {cfg.requireEmailVerification && codeSent && (
            <div>
              <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: tv.textMuted }}>Код из письма</label>
              <input value={verifyCode} onChange={e => setVerifyCode(e.target.value)} placeholder="123456" maxLength={6}
                className="w-full border text-sm p-3.5 outline-none transition-all font-mono tracking-[0.3em] text-center"
                style={{ background: tv.inputBg, borderColor: p + '30', borderRadius: r, color: tv.text }} />
            </div>
          )}

          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: tv.textMuted }}>Пароль</label>
            <div className="relative">
              <input type={showPass ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="••••••••"
                className="w-full border text-sm p-3.5 outline-none transition-all pr-12"
                style={{ background: tv.inputBg, borderColor: p + '30', borderRadius: r, color: tv.text }} />
              <button onClick={() => setShowPass(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: p + '60' }}>
                {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 py-2.5 px-3 rounded-2xl text-xs" style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#f87171' }}>
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}

          <button onClick={handleSubmit} disabled={loading}
            className="w-full py-4 font-black text-[10px] uppercase tracking-widest text-white transition-all disabled:opacity-50 flex items-center justify-center gap-2 mt-1"
            style={{ background: p, borderRadius: r, boxShadow: `0 6px 20px ${p}40` }}>
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
            {loading ? 'Загрузка...' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
          </button>
        </div>
      </div>
    </div>
  );
};
// ─── Admin Picker (User selects admin) ──────────────────────────────────────────

const AdminPicker: React.FC<{
  site: PublicSite; session: ChatSession; existingConvs: Conversation[];
  admins: AdminInfo[]; onSelect: (conv: Conversation) => void; onLogout: () => void;
}> = ({ site, session, existingConvs, admins, onSelect, onLogout }) => {
  const cfg = site.config;
  const p = cfg.primaryColor || '#6366f1';
  const font = cfg.fontFamily || 'Manrope, sans-serif';
  const r = getRadius(cfg);
  const tv = themeVars(cfg);

  const startOrOpenConv = async (admin: AdminInfo) => {
    const ex = existingConvs.find(c => c.admin_id === admin.id);
    if (ex) { onSelect(ex); return; }
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/conversation`, {
        method: 'POST',
        body: JSON.stringify({ user_id: session.id, user_name: session.display_name, admin_id: admin.id })
      });
      onSelect(data);
    } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: tv.bg, fontFamily: font, color: tv.text }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b" style={{ borderColor: p + '20', background: tv.bg }}>
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: p }} />
          <span className="font-black" style={{ color: p, fontSize: getFontSize(cfg) }}>{cfg.logoText || site.name}</span>
        </div>
        <button onClick={onLogout} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest transition-colors" style={{ color: p + '60' }}>
          <LogOut className="w-3.5 h-3.5" /> Выйти
        </button>
      </div>

      <div className="flex-1 p-4 sm:p-6 max-w-lg mx-auto w-full overflow-y-auto">
        <div className="mb-6">
          <h2 className="font-black text-lg mb-1" style={{ color: tv.text }}>Выберите специалиста</h2>
          <p className="text-xs" style={{ color: tv.textMuted }}>Выберите администратора для начала диалога</p>
        </div>

        <div className="space-y-3">
          {admins.filter(a => a).map(admin => {
            const hasConv = existingConvs.some(c => c.admin_id === admin.id);
            return (
              <button key={admin.id} onClick={() => startOrOpenConv(admin)}
                className="w-full flex items-center gap-4 p-4 sm:p-5 transition-all text-left"
                style={{ background: tv.surface, border: `1px solid ${p}20`, borderRadius: r }}>
                <Avatar name={admin.display_name} color={admin.avatar_color} size="w-12 h-12"
                  online={cfg.showOnlineStatus ? admin.is_online : undefined} />
                <div className="flex-1 min-w-0">
                  <p className="font-black text-sm" style={{ color: tv.text }}>{admin.display_name}</p>
                  {admin.bio && <p className="text-xs mt-0.5 truncate" style={{ color: tv.textMuted }}>{admin.bio}</p>}
                  {cfg.showOnlineStatus && (
                    <div className={`flex items-center gap-1.5 mt-1 text-[9px] font-bold uppercase ${admin.is_online ? 'text-emerald-400' : 'text-zinc-600'}`}>
                      <div className={`w-1.5 h-1.5 rounded-full ${admin.is_online ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                      {admin.is_online ? 'Онлайн' : 'Офлайн'}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {hasConv && <div className="w-2 h-2 rounded-full" style={{ background: p }} />}
                  <ChevronRight className="w-4 h-4" style={{ color: p + '50' }} />
                </div>
              </button>
            );
          })}

          {/* Групповой чат */}
          {cfg.groupChatEnabled && (
            <button onClick={() => onSelect({ id: '__group__', site_id: site.id, user_id: session.id, admin_id: '__group__', user_name: session.display_name, admin_name: 'Чат', last_message_at: 0, last_message_preview: '', unread_admin: 0, unread_user: 0 })}
              className="w-full flex items-center gap-4 p-4 sm:p-5 transition-all text-left"
              style={{ background: p + '10', border: `1px solid ${p}30`, borderRadius: r }}>
              <div className="w-12 h-12 rounded-full flex items-center justify-center text-2xl" style={{ background: p + '20' }}>💬</div>
              <div className="flex-1">
                <p className="font-black text-sm" style={{ color: tv.text }}>Общий чат</p>
                <p className="text-xs mt-0.5" style={{ color: p + '80' }}>Все участники вместе</p>
              </div>
              <Layers className="w-4 h-4" style={{ color: p + '60' }} />
            </button>
          )}
        </div>

        {existingConvs.length > 0 && (
          <div className="mt-8">
            <p className="text-[9px] font-black uppercase tracking-widest mb-3" style={{ color: p + '60' }}>Мои диалоги</p>
            <div className="space-y-2">
              {existingConvs.map(conv => (
                <button key={conv.id} onClick={() => onSelect(conv)}
                  className="w-full flex items-center gap-3 p-3 sm:p-4 text-left transition-all"
                  style={{ background: tv.surface2, border: `1px solid ${p}15`, borderRadius: r }}>
                  <Avatar name={conv.admin_name} color={p} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold" style={{ color: tv.text }}>{conv.admin_name}</p>
                    {conv.last_message_preview && (
                      <p className="text-xs truncate mt-0.5" style={{ color: tv.textMuted }}>{conv.last_message_preview}</p>
                    )}
                  </div>
                  {conv.unread_user > 0 && (
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black text-white shrink-0" style={{ background: p }}>
                      {conv.unread_user}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── User Chat ──────────────────────────────────────────────────────────────────

const UserChat: React.FC<{
  site: PublicSite; session: ChatSession; conversation: Conversation;
  admins: AdminInfo[]; onBack: () => void; onLogout: () => void;
}> = ({ site, session, conversation, admins, onBack, onLogout }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const cfg = site.config;
  const p = cfg.primaryColor || '#6366f1';
  const r = getRadius(cfg);

  // If group chat
  if (conversation.id === '__group__') {
    return (
      <div className="flex flex-col h-screen overflow-hidden" style={{ background: cfg.bgColor || '#09090b', fontFamily: cfg.fontFamily || 'Manrope, sans-serif' }}>
        <div className="flex items-center gap-3 px-4 sm:px-5 py-3 border-b shrink-0" style={{ borderColor: p + '20' }}>
          <button onClick={onBack} className="p-2 rounded-xl hover:bg-white/10 transition-all"><ArrowLeft className="w-4 h-4" style={{ color: p }} /></button>
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg" style={{ background: p + '20' }}>💬</div>
          <div className="flex-1">
            <p className="font-black text-sm" style={{ color: themeVars(cfg).text }}>Общий чат</p>
            <p className="text-[9px] font-bold uppercase tracking-widest" style={{ color: p + '80' }}>Все участники</p>
          </div>
          <button onClick={onLogout} className="p-2 rounded-xl hover:bg-white/10 transition-all"><LogOut className="w-4 h-4" style={{ color: p + '60' }} /></button>
        </div>
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-hidden"><GroupChat site={site} session={session} /></div>
        </div>
      </div>
    );
  }

  const admin = admins.find(a => a.id === conversation.admin_id);

  const loadMessages = useCallback(async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/messages/${conversation.id}?role=user&session_id=${session.id}`);
      if (Array.isArray(data)) {
        // Сохраняем optimistic-сообщения у которых ещё нет реального аналога
        setMessages(prev => {
          const opts = prev.filter(m => m.id.startsWith('opt_'));
          const serverIds = new Set(data.map((m: Message) => m.id));
          const stillPending = opts.filter(o =>
            !data.some((r: Message) =>
              r.from_id === o.from_id &&
              r.media_url === o.media_url &&
              r.text === o.text &&
              Math.abs(r.created_at - o.created_at) < 10000
            )
          );
          return [...data, ...stillPending].sort((a, b) => a.created_at - b.created_at);
        });
      }
    } catch { } finally { setLoading(false); }
  }, [site.slug, conversation.id, session.id]);

  useEffect(() => {
    loadMessages();
    const interval = setInterval(loadMessages, POLL);
    return () => clearInterval(interval);
  }, [loadMessages]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length]);

  const handleSend = async (text: string, mediaUrl?: string, mediaType?: string, sticker?: string, duration?: number) => {
    // Optimistic: показываем сообщение мгновенно
    const optId = `opt_${Date.now()}`;
    const optimistic: Message = {
      id: optId, conversation_id: conversation.id, site_id: site.id,
      from_id: session.id, from_name: session.display_name || session.username || 'Пользователь',
      from_role: session.role, text: text || null,
      media_url: mediaUrl || null, media_type: (mediaType as any) || null,
      sticker_emoji: sticker || null, duration: duration || null,
      created_at: Date.now(), is_read: false, is_deleted: false,
    };
    setMessages(prev => [...prev, optimistic]);

    try {
      await apiFetch(`${API}/chat/site/${site.slug}/message`, {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: conversation.id, from_id: session.id,
          from_name: session.display_name || session.username || 'Пользователь',
          from_role: session.role, text: text || null,
          media_url: mediaUrl, media_type: mediaType, sticker_emoji: sticker,
          duration: duration || null
        })
      });
      // После успешной отправки — загружаем реальные данные
      // Задержка нужна чтобы Supabase успел записать
      setTimeout(() => loadMessages(), 300);
      setTimeout(() => loadMessages(), 1200);
    } catch {
      // При ошибке убираем optimistic
      setMessages(prev => prev.filter(m => m.id !== optId));
    }
  };

  const grouped: { date: string; msgs: Message[] }[] = [];
  for (const msg of messages) {
    const d = fmtDate(msg.created_at);
    if (!grouped.length || grouped[grouped.length-1].date !== d) grouped.push({ date: d, msgs: [] });
    grouped[grouped.length-1].msgs.push(msg);
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: themeVars(cfg).bg, fontFamily: cfg.fontFamily || 'Manrope, sans-serif', color: themeVars(cfg).text }}>
      {/* Header — sticky, не прокручивается */}
      <div className="flex items-center gap-3 px-3 sm:px-5 py-3 border-b shrink-0" style={{ borderColor: p + '20', background: themeVars(cfg).bg }}>
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-white/10 transition-all"><ArrowLeft className="w-4 h-4" style={{ color: p }} /></button>
        {admin ? (
          <Avatar name={admin.display_name} color={admin.avatar_color} size="w-9 h-9"
            online={cfg.showOnlineStatus ? admin.is_online : undefined} />
        ) : (
          <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: p + '20' }}>
            <Shield className="w-4 h-4" style={{ color: p }} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="font-black text-sm truncate" style={{ color: themeVars(cfg).text }}>{conversation.admin_name}</p>
          {cfg.showOnlineStatus && admin && (
            <p className={`text-[9px] font-bold uppercase ${admin.is_online ? 'text-emerald-400' : 'text-zinc-600'}`}>
              {admin.is_online ? '● Онлайн' : '○ Офлайн'}
            </p>
          )}
        </div>
        <button onClick={onLogout} className="p-2 rounded-xl transition-all" style={{ color: p + '60' }}
          onMouseEnter={e => e.currentTarget.style.background = themeVars(cfg).surface}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
          <LogOut className="w-3.5 h-3.5" /></button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 min-h-0">
        {loading ? (
          <div className="flex justify-center py-8"><RefreshCw className="w-5 h-5 animate-spin" style={{ color: themeVars(cfg).textFaint }} /></div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-16 text-center">
            <MessageCircle className="w-12 h-12 mb-4" style={{ color: p + '25' }} />
            <p className="font-black text-sm" style={{ color: themeVars(cfg).textMuted }}>Напишите первое сообщение</p>
          </div>
        ) : grouped.map(({ date, msgs }) => (
          <div key={date}>
            <div className="flex justify-center my-4">
              <span className="text-[10px] font-bold px-3 py-1 rounded-full" style={{ background: p + '15', color: p + 'aa' }}>{date}</span>
            </div>
            {msgs.map(msg => (
              <MessageBubble key={msg.id} msg={msg} session={session} primary={p} cfg={cfg} />
            ))}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <MessageInput onSend={handleSend} primary={p} commands={cfg.commands || []} cfg={cfg} />
    </div>
  );
};

// ─── Admin Chat Panel ────────────────────────────────────────────────────────────

const AdminChatPanel: React.FC<{
  site: PublicSite; session: ChatSession; onLogout: () => void;
}> = ({ site, session, onLogout }) => {
  const [tab, setTab] = useState<'chats' | 'group' | 'users' | 'broadcast'>('chats');
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [users, setUsers] = useState<SiteUser[]>([]);
  const [broadcastText, setBroadcastText] = useState('');
  const [sending, setSending] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [showBanModal, setShowBanModal] = useState<SiteUser | null>(null);
  const [banReason, setBanReason] = useState('');
  const [warnReason, setWarnReason] = useState('');
  const [showWarnModal, setShowWarnModal] = useState<SiteUser | null>(null);
  const [muteUserId, setMuteUserId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<NodeJS.Timeout>();

  const p = site.config.primaryColor || '#6366f1';
  const font = site.config.fontFamily || 'Manrope, sans-serif';
  const tv = themeVars(site.config);

  // Set admin online on mount
  useEffect(() => {
    if (session.role === 'admin' || session.role === 'owner') {
      fetch(`${API}/chat/sites/${site.id}/admins/${session.id}/online`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_online: true })
      });
    }
    return () => {
      fetch(`${API}/chat/sites/${site.id}/admins/${session.id}/online`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_online: false })
      });
    };
  }, []);

  const toggleOnline = async () => {
    const next = !isOnline;
    setIsOnline(next);
    await fetch(`${API}/chat/sites/${site.id}/admins/${session.id}/online`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_online: next })
    });
  };

  const loadConvs = async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/conversations?role=${session.role}&session_id=${session.id}`);
      setConvs(Array.isArray(data) ? data : []);
    } catch { }
  };

  const loadMessages = async (convId: string) => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/messages/${convId}?role=${session.role}&session_id=${session.id}`);
      if (Array.isArray(data)) {
        setMessages(prev => {
          const opts = prev.filter(m => m.id.startsWith('opt_'));
          const stillPending = opts.filter(o =>
            !data.some((r: Message) =>
              r.from_id === o.from_id &&
              r.media_url === o.media_url &&
              r.text === o.text &&
              Math.abs(r.created_at - o.created_at) < 10000
            )
          );
          return [...data, ...stillPending].sort((a, b) => a.created_at - b.created_at);
        });
      }
    } catch { }
  };

  const loadUsers = async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/users?role=${session.role}`);
      setUsers(Array.isArray(data) ? data : []);
    } catch { }
  };

  useEffect(() => {
    loadConvs();
    pollRef.current = setInterval(loadConvs, POLL);
    return () => clearInterval(pollRef.current);
  }, [site.slug]);

  useEffect(() => {
    if (tab === 'users') loadUsers();
  }, [tab]);

  useEffect(() => {
    if (!selectedConv) return;
    loadMessages(selectedConv.id);
    const iv = setInterval(() => loadMessages(selectedConv.id), POLL);
    return () => clearInterval(iv);
  }, [selectedConv?.id]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length]);

  const handleSend = async (text: string, mediaUrl?: string, mediaType?: string, sticker?: string, duration?: number) => {
    if (!selectedConv) return;
    const optId = `opt_${Date.now()}`;
    const optimistic: Message = {
      id: optId, conversation_id: selectedConv.id, site_id: site.id,
      from_id: session.id, from_name: session.display_name, from_role: session.role,
      text: text || null, media_url: mediaUrl || null, media_type: (mediaType as any) || null,
      sticker_emoji: sticker || null, duration: duration || null,
      created_at: Date.now(), is_read: false, is_deleted: false,
    };
    setMessages(prev => [...prev, optimistic]);

    try {
      await apiFetch(`${API}/chat/site/${site.slug}/message`, {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: selectedConv.id, from_id: session.id,
          from_name: session.display_name, from_role: session.role,
          text: text || null, media_url: mediaUrl, media_type: mediaType, sticker_emoji: sticker,
          duration: duration || null
        })
      });
      loadConvs();
      setTimeout(() => loadMessages(selectedConv.id), 300);
      setTimeout(() => loadMessages(selectedConv.id), 1200);
    } catch {
      setMessages(prev => prev.filter(m => m.id !== optId));
    }
  };

  const handleBroadcast = async () => {
    if (!broadcastText.trim()) return;
    setSending(true);
    try {
      const result = await apiFetch(`${API}/chat/site/${site.slug}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ role: session.role, from_id: session.id, from_name: session.display_name, text: broadcastText })
      });
      setBroadcastText('');
      alert(`✅ Рассылка отправлена в ${result.sent_to ?? 0} диалог(ов)`);
    } catch (e: any) { alert(e.message || 'Ошибка рассылки'); } finally { setSending(false); }
  };

  const handleBan = async (user: SiteUser, ban: boolean) => {
    await apiFetch(`${API}/chat/site/${site.slug}/users/${user.id}/ban`, {
      method: 'POST', body: JSON.stringify({ role: session.role, is_banned: ban, ban_reason: banReason })
    });
    setBanReason(''); setShowBanModal(null);
    loadUsers();
  };

  const handleWarn = async (user: SiteUser) => {
    if (!warnReason.trim()) return;
    const data = await apiFetch(`${API}/chat/site/${site.slug}/users/${user.id}/warn`, {
      method: 'POST',
      body: JSON.stringify({ role: session.role, admin_id: session.id, admin_name: session.display_name, reason: warnReason })
    });
    setWarnReason(''); setShowWarnModal(null);
    if (data.auto_banned) alert('Пользователь автоматически забанен');
    loadUsers();
  };

  const handleMute = async (userId: string, minutes: number) => {
    const muted_until_ms = minutes > 0 ? Date.now() + minutes * 60000 : 0;
    await apiFetch(`${API}/chat/site/${site.slug}/users/${userId}/mute`, {
      method: 'POST', body: JSON.stringify({ role: session.role, muted_until_ms })
    });
    setMuteUserId(null);
    loadUsers();
  };

  const TABS = [
    { id: 'chats', label: 'Диалоги', icon: MessageCircle },
    ...(site.config.groupChatEnabled ? [{ id: 'group', label: 'Чат', icon: Layers }] : []),
  ] as const;

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: tv.bg, fontFamily: font, color: tv.text }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-3 sm:px-5 py-3 border-b shrink-0" style={{ borderColor: p + '20', background: tv.bg }}>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: p }} />
          <span className="font-black text-sm truncate" style={{ color: p }}>{site.config.logoText || site.name}</span>
          <span className="text-[8px] font-mono hidden sm:block shrink-0" style={{ color: tv.textFaint }}>@{site.slug}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Online toggle */}
          <button onClick={toggleOnline}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl transition-all text-[9px] font-black uppercase border"
            style={{
              background: isOnline ? '#10b98115' : '#71717a15',
              color: isOnline ? '#10b981' : '#71717a',
              borderColor: isOnline ? '#10b98130' : '#71717a30'
            }}>
            {isOnline ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            <span className="hidden sm:inline">{isOnline ? 'Онлайн' : 'Офлайн'}</span>
          </button>
          <Avatar name={session.display_name} color={session.avatar_color || p} size="w-8 h-8" />
          <button onClick={onLogout} className="p-2 rounded-xl transition-all"
            onMouseEnter={e => e.currentTarget.style.background = tv.surface}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
            <LogOut className="w-3.5 h-3.5" style={{ color: p + '70' }} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b shrink-0 overflow-x-auto no-scrollbar" style={{ borderColor: p + '15', background: tv.bg }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className="flex items-center gap-1.5 px-3 sm:px-5 py-2.5 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap flex-1 sm:flex-none justify-center"
            style={{ borderColor: tab === t.id ? p : 'transparent', color: tab === t.id ? p : tv.textMuted }}>
            <t.icon className="w-3.5 h-3.5" /><span className="hidden sm:inline">{t.label}</span>
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Ban modal */}
        {showBanModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/80" onClick={() => setShowBanModal(null)} />
            <div className="relative w-full max-w-sm bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4">
              <p className="text-white font-black">Забанить {showBanModal.username}?</p>
              <input value={banReason} onChange={e => setBanReason(e.target.value)} placeholder="Причина..."
                className="w-full bg-black border border-zinc-800 text-white p-3 rounded-xl outline-none text-sm" />
              <div className="flex gap-3">
                <button onClick={() => setShowBanModal(null)} className="flex-1 py-3 rounded-xl bg-zinc-800 text-zinc-400 text-xs font-black uppercase">Отмена</button>
                <button onClick={() => handleBan(showBanModal, true)} className="flex-1 py-3 rounded-xl bg-rose-600 text-white text-xs font-black uppercase">Забанить</button>
              </div>
            </div>
          </div>
        )}

        {/* Warn modal */}
        {showWarnModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/80" onClick={() => setShowWarnModal(null)} />
            <div className="relative w-full max-w-sm bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4">
              <p className="text-white font-black flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-400" /> Варн для {showWarnModal.username}</p>
              <input value={warnReason} onChange={e => setWarnReason(e.target.value)} placeholder="Причина варна..."
                className="w-full bg-black border border-zinc-800 text-white p-3 rounded-xl outline-none text-sm"
                onKeyDown={e => e.key === 'Enter' && handleWarn(showWarnModal)} />
              <div className="flex gap-3">
                <button onClick={() => setShowWarnModal(null)} className="flex-1 py-3 rounded-xl bg-zinc-800 text-zinc-400 text-xs font-black uppercase">Отмена</button>
                <button onClick={() => handleWarn(showWarnModal)} disabled={!warnReason.trim()} className="flex-1 py-3 rounded-xl bg-amber-600 text-white text-xs font-black uppercase disabled:opacity-40">+Варн</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Chats ── */}
        {tab === 'chats' && (
          <>
            {/* Conv list - sidebar on desktop, full on mobile */}
            <div className={`${selectedConv ? 'hidden sm:flex' : 'flex'} flex-col w-full sm:w-72 border-r shrink-0`} style={{ borderColor: p + '15' }}>
              <div className="p-3 border-b" style={{ borderColor: p + '10' }}>
                <p className="text-[9px] font-black uppercase tracking-widest" style={{ color: p }}>Диалоги ({convs.length})</p>
              </div>
              <div className="flex-1 overflow-y-auto no-scrollbar">
                {convs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full py-16 text-center px-4">
                    <MessageCircle className="w-10 h-10 mb-3" style={{ color: p + '20' }} />
                    <p className="text-xs font-bold" style={{ color: tv.textMuted }}>Нет диалогов</p>
                  </div>
                ) : convs.map(conv => (
                  <button key={conv.id} onClick={() => setSelectedConv(conv)}
                    className={`w-full flex items-center gap-3 px-3 py-3 border-b text-left transition-all ${selectedConv?.id === conv.id ? 'border-l-2' : ''}`}
                    style={{ borderColor: p + '10', borderLeftColor: selectedConv?.id === conv.id ? p : 'transparent',
                      background: selectedConv?.id === conv.id ? p + '08' : 'transparent' }}
                    onMouseEnter={e => { if (selectedConv?.id !== conv.id) e.currentTarget.style.background = tv.surface; }}
                    onMouseLeave={e => { if (selectedConv?.id !== conv.id) e.currentTarget.style.background = 'transparent'; }}>
                    <Avatar name={conv.user_name} size="w-9 h-9" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-black truncate" style={{ color: tv.text }}>{conv.user_name}</p>
                        {conv.last_message_at > 0 && <span className="text-[9px] shrink-0 ml-1" style={{ color: tv.textFaint }}>{fmtTime(conv.last_message_at)}</span>}
                      </div>
                      {conv.last_message_preview && (
                        <p className="text-[10px] truncate mt-0.5" style={{ color: tv.textMuted }}>{conv.last_message_preview}</p>
                      )}
                    </div>
                    {conv.unread_admin > 0 && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black text-white shrink-0" style={{ background: p }}>
                        {conv.unread_admin}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Message area */}
            {selectedConv ? (
              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center gap-3 px-3 sm:px-4 py-2.5 border-b shrink-0" style={{ borderColor: p + '15', background: tv.bg }}>
                  <button onClick={() => setSelectedConv(null)} className="sm:hidden p-1.5 rounded-xl transition-all"
                    style={{ color: p }}
                    onMouseEnter={e => e.currentTarget.style.background = tv.surface}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <ArrowLeft className="w-4 h-4" />
                  </button>
                  <Avatar name={selectedConv.user_name} size="w-8 h-8" />
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-sm truncate" style={{ color: tv.text }}>{selectedConv.user_name}</p>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-3 sm:p-4 min-h-0">
                  {messages.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <p className="text-xs font-bold" style={{ color: tv.textMuted }}>Начните диалог</p>
                    </div>
                  ) : (() => {
                    const grouped: { date: string; msgs: Message[] }[] = [];
                    for (const msg of messages) {
                      const d = fmtDate(msg.created_at);
                      if (!grouped.length || grouped[grouped.length-1].date !== d) grouped.push({ date: d, msgs: [] });
                      grouped[grouped.length-1].msgs.push(msg);
                    }
                    return grouped.map(({ date, msgs }) => (
                      <div key={date}>
                        <div className="flex justify-center my-4">
                          <span className="text-[10px] font-bold px-3 py-1 rounded-full" style={{ background: p + '15', color: p + 'aa' }}>{date}</span>
                        </div>
                        {msgs.map(msg => (
                          <MessageBubble key={msg.id} msg={msg} session={session} primary={p} cfg={site.config} />
                        ))}
                      </div>
                    ));
                  })()}
                  <div ref={bottomRef} />
                </div>
                <MessageInput onSend={handleSend} primary={p} commands={[]} placeholder={`Ответить ${selectedConv.user_name}...`} cfg={site.config} />
              </div>
            ) : (
              <div className="hidden sm:flex flex-1 items-center justify-center">
                <div className="text-center">
                  <MessageCircle className="w-12 h-12 mx-auto mb-3" style={{ color: p + '20' }} />
                  <p className="text-xs font-bold" style={{ color: tv.textMuted }}>Выберите диалог</p>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Group chat tab ── */}
        {tab === 'group' && (
          <div className="flex-1 flex flex-col min-w-0">
            <div className="flex-1 overflow-hidden h-full"><GroupChat site={site} session={session} /></div>
          </div>
        )}

        {/* ── Users ── */}
        {tab === 'users' && (
          <div className="flex-1 overflow-y-auto p-3 sm:p-5 min-h-0">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-black" style={{ color: tv.text }}>Пользователи ({users.length})</h2>
            </div>
            <div className="space-y-2">
              {users.map(u => {
                const muted = (u.muted_until || 0) > Date.now();
                return (
                  <div key={u.id} className="flex items-center gap-3 p-3 rounded-2xl border transition-all"
                    style={{ background: tv.surface2, borderColor: p + '12' }}>
                    <Avatar name={u.username} size="w-9 h-9" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-bold text-sm" style={{ color: u.is_banned ? tv.textFaint : tv.text, textDecoration: u.is_banned ? 'line-through' : 'none' }}>{u.username}</p>
                        {u.is_banned && <span className="text-[8px] bg-rose-500/20 text-rose-400 px-1.5 py-0.5 rounded-full font-black">Бан</span>}
                        {muted && <span className="text-[8px] bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded-full font-black">Мут</span>}
                        {(u.warn_count || 0) > 0 && <span className="text-[8px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded-full font-black">{u.warn_count}⚠</span>}
                      </div>
                      {u.email && <p className="text-[9px] mt-0.5 truncate" style={{ color: tv.textMuted }}>{u.email}</p>}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button onClick={() => setShowWarnModal(u)}
                        className="p-1.5 rounded-xl transition-all" style={{ background: '#f59e0b15', color: '#f59e0b' }}>
                        <AlertTriangle className="w-3.5 h-3.5" />
                      </button>
                      {muted ? (
                        <button onClick={() => handleMute(u.id, 0)}
                          className="p-1.5 rounded-xl transition-all" style={{ background: '#10b98115', color: '#10b981' }}>
                          <Volume2 className="w-3.5 h-3.5" />
                        </button>
                      ) : (
                        <button onClick={() => setMuteUserId(muteUserId === u.id ? null : u.id)}
                          className="p-1.5 rounded-xl transition-all" style={{ background: '#f9731615', color: '#f97316' }}>
                          <VolumeX className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {u.is_banned ? (
                        <button onClick={() => handleBan(u, false)}
                          className="p-1.5 rounded-xl transition-all" style={{ background: '#10b98115', color: '#10b981' }}>
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      ) : (
                        <button onClick={() => setShowBanModal(u)}
                          className="p-1.5 rounded-xl transition-all" style={{ background: '#ef444415', color: '#ef4444' }}>
                          <Ban className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    {muteUserId === u.id && !muted && (
                      <div className="absolute right-16 z-10 border rounded-2xl overflow-hidden shadow-xl"
                        style={{ background: tv.bg, borderColor: tv.border }}>
                        {[10, 30, 60, 360, 1440, 10080].map(m => (
                          <button key={m} onClick={() => handleMute(u.id, m)}
                            className="flex items-center gap-2 w-full px-4 py-2 text-xs text-left whitespace-nowrap transition-all"
                            style={{ color: tv.text }}
                            onMouseEnter={e => e.currentTarget.style.background = tv.surface}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                            <VolumeX className="w-3 h-3 text-orange-400" />
                            {m < 60 ? `${m} мин` : m < 1440 ? `${m/60} ч` : m < 10080 ? `${m/1440} дн` : '7 дней'}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
              {users.length === 0 && (
                <div className="text-center py-12">
                  <Users className="w-10 h-10 mx-auto mb-3" style={{ color: tv.textFaint }} />
                  <p className="font-bold text-sm" style={{ color: tv.textMuted }}>Нет пользователей</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Broadcast ── */}
        {tab === 'broadcast' && (
          <div className="flex-1 p-4 sm:p-6">
            <h2 className="text-lg font-black mb-5" style={{ color: tv.text }}>Рассылка</h2>
            <div className="max-w-2xl">
              <div className="p-4 sm:p-5 rounded-[1.5rem] border mb-4" style={{ background: tv.surface, borderColor: p + '20' }}>
                <p className="text-[9px] font-black uppercase tracking-wider mb-3" style={{ color: p }}>Сообщение всем пользователям</p>
                <textarea value={broadcastText} onChange={e => setBroadcastText(e.target.value)}
                  placeholder="Текст сообщения..." rows={5}
                  className="w-full bg-transparent text-sm outline-none resize-none leading-relaxed"
                  style={{ color: tv.text }} />
              </div>
              <button onClick={handleBroadcast} disabled={!broadcastText.trim() || sending}
                className="flex items-center gap-2 px-6 sm:px-8 py-3.5 sm:py-4 rounded-2xl font-black text-[10px] uppercase tracking-wider disabled:opacity-40 transition-all"
                style={{ background: p, color: '#fff', boxShadow: `0 4px 16px ${p}40` }}>
                {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                {sending ? 'Отправка...' : 'Отправить всем'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── License Expired Overlay ─────────────────────────────────────────────────────

const LicenseExpiredOverlay: React.FC<{ siteName: string; primary: string; bg: string }> = ({ siteName, primary, bg }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: bg }}>
    <div className="flex flex-col items-center gap-6 p-8 max-w-sm w-full text-center">
      <div className="w-20 h-20 rounded-3xl flex items-center justify-center" style={{ background: primary + '15', border: `2px solid ${primary}30` }}>
        <Shield className="w-10 h-10" style={{ color: primary }} />
      </div>
      <div>
        <p className="text-white text-2xl font-black mb-2">{siteName}</p>
        <p className="font-black text-lg mb-1" style={{ color: primary }}>Лицензия истекла</p>
        <p className="text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Доступ к этому чат-сайту временно приостановлен. Пожалуйста, свяжитесь с владельцем платформы для продления лицензии.
        </p>
      </div>
      <div className="w-full p-4 rounded-2xl flex items-center gap-3" style={{ background: primary + '10', border: `1px solid ${primary}25` }}>
        <AlertCircle className="w-5 h-5 shrink-0" style={{ color: primary }} />
        <p className="text-xs font-bold text-left" style={{ color: primary + 'cc' }}>Сервис временно недоступен</p>
      </div>
    </div>
  </div>
);

// ─── Root ────────────────────────────────────────────────────────────────────────

const ChatSiteApp: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [sp] = useSearchParams();
  const forceAdmin = sp.get('as') === 'admin';

  const [site, setSite] = useState<PublicSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [licenseExpired, setLicenseExpired] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(() => {
    try { const s = localStorage.getItem(`cs_session_${slug}`); return s ? JSON.parse(s) : null; } catch { return null; }
  });
  const [admins, setAdmins] = useState<AdminInfo[]>([]);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);

  useEffect(() => {
    apiFetch(`${API}/chat/site/${slug}/public`)
      .then(data => {
        setSite(data);
        // Check license status for public site
        fetch(`${API}/chat/site/${slug}/license-status`)
          .then(r => r.json())
          .then(lic => { if (lic && lic.expired) setLicenseExpired(true); })
          .catch(() => {});
      })
      .catch(() => setSite(null))
      .finally(() => setLoading(false));
    apiFetch(`${API}/chat/site/${slug}/admins`).then(setAdmins).catch(() => {});
  }, [slug]);

  useEffect(() => {
    if (!session || !site || session.role !== 'user') return;
    apiFetch(`${API}/chat/site/${slug}/conversations?role=user&session_id=${session.id}`)
      .then(setConvs).catch(() => {});
  }, [session?.id, site]);

  const handleAuth = (s: ChatSession) => {
    setSession(s);
    localStorage.setItem(`cs_session_${slug}`, JSON.stringify(s));
  };

  const handleLogout = () => {
    if (session?.role === 'admin' || session?.role === 'owner') {
      fetch(`${API}/chat/sites/${site?.id}/admins/${session.id}/online`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_online: false })
      });
    }
    setSession(null);
    localStorage.removeItem(`cs_session_${slug}`);
    setSelectedConv(null);
    setConvs([]);
  };

  if (loading) return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <RefreshCw className="w-6 h-6 text-white/20 animate-spin" />
    </div>
  );

  if (!site) return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <div className="text-center">
        <p className="text-6xl font-black text-white/10 mb-3">404</p>
        <p className="text-white/30 font-bold text-sm">Сайт не найден</p>
      </div>
    </div>
  );

  // Show license expired overlay for all non-admin users (including unauthenticated)
  if (licenseExpired && session?.role !== 'admin' && session?.role !== 'owner') {
    const p = site.config?.primaryColor || '#6366f1';
    const bg = site.config?.bgColor || '#09090b';
    return <LicenseExpiredOverlay siteName={site.name} primary={p} bg={bg} />;
  }

  if (!session) return <AuthScreen site={site} forceAdmin={forceAdmin} onAuth={handleAuth} />;

  if (session.role === 'admin' || session.role === 'owner') {
    return <AdminChatPanel site={site} session={session} onLogout={handleLogout} />;
  }

  if (selectedConv) {
    return (
      <UserChat
        site={site} session={session} conversation={selectedConv} admins={admins}
        onBack={() => setSelectedConv(null)} onLogout={handleLogout}
      />
    );
  }

  return (
    <AdminPicker
      site={site} session={session} existingConvs={convs} admins={admins}
      onSelect={conv => setSelectedConv(conv)}
      onLogout={handleLogout}
    />
  );
};

export default ChatSiteApp;

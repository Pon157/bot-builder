import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Send, LogOut, Ban, Megaphone, RefreshCw, MessageCircle, UserPlus,
  ChevronRight, Check, X, Shield, AlertCircle, Image, Smile,
  ArrowLeft, BarChart3, Users, Hash, AtSign, Mail, Eye, EyeOff,
  Paperclip, Play, File as FileIcon, Star, Plus
} from 'lucide-react';

// ─── Constants ─────────────────────────────────────────────────────────────────

const API = '/api';
const POLL = 2500;

const EMOJI_CATEGORIES = [
  { name: 'Лица', icon: '😊', emojis: ['😀','😃','😄','😁','😆','😅','😂','🤣','😊','😇','🥰','😍','🤩','😘','😗','😙','😚','🙂','🤗','🤔','🤐','😐','😑','😶','😏','😒','🙄','😬','😔','😪','😴','😷','🤒','🤕','🤢','🤧','🥵','🥶','🥴','😵','🤯','🥳','😎','🤓','😕','😟','🙁','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','😤','😡','😠','🤬','😈','💀','👻','👾','🤖','💩','🤡'] },
  { name: 'Жесты', icon: '👋', emojis: ['👋','🤚','🖐','✋','🖖','👌','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','👇','☝️','👍','👎','✊','👊','🤛','🤜','👏','🙌','👐','🤲','🤝','🙏','💪','🦾','👀','👄','💋','❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💯','💢','💥','💫','✨','🔥','💧','💦','⚡'] },
  { name: 'Животные', icon: '🐶', emojis: ['🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🐔','🐧','🐦','🦆','🦅','🦉','🦇','🐺','🐗','🐴','🦄','🐝','🐛','🦋','🐌','🐞','🐜','🐢','🐍','🦎','🐙','🦑','🦐','🦀','🐡','🐠','🐟','🐬','🐳','🦈','🐊','🐅','🐆','🦓','🦍','🐘','🦛','🦏','🐪','🦒','🦘','🐄','🐑','🐐','🦃','🦚','🦜','🦢','🕊️','🐇','🦝','🦡','🦦','🐁','🐀','🐿️','🦔'] },
  { name: 'Еда', icon: '🍕', emojis: ['🍏','🍎','🍐','🍊','🍋','🍌','🍉','🍇','🍓','🫐','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🥑','🥦','🥒','🌽','🍄','🍞','🥐','🧀','🥚','🍳','🥞','🧇','🥓','🍗','🍖','🌭','🍔','🍟','🍕','🥪','🌮','🌯','🍝','🍜','🍲','🍛','🍣','🍱','🍤','🍙','🍚','🧁','🍰','🎂','🍮','🍭','🍬','🍫','🍿','🍩','🍪','🌰','🍯','🧃','🥤','☕','🍵','🍺','🍻','🥂','🍷','🍸','🍹','🧉','🍾'] },
  { name: 'Объекты', icon: '💡', emojis: ['🎁','🎀','🎊','🎉','🎈','🎏','🎑','🧧','💌','📱','💻','🖥️','📷','📹','🎥','📞','☎️','📺','📻','💡','🔦','🕯️','💰','💳','💎','📿','💍','💄','👑','👒','🎩','🎒','👜','👛','👝','🛡️','🔑','🗝️','🔨','🔧','🔩','🔫','🏹','⚗️','🔭','🔬','💊','🩺','🩻','🧬','🧪','🧫','📝','✏️','🖊️','📏','📐','✂️','🔒','🔓','🔔','🔕','🎵','🎶','🎼','🎹','🎸','🎺','🎻','🥁','🎮','🎲','🎯','🎱','🎳','⚽','🏀','🏈','⚾','🎾','🏐','🏉','🎿','🛷','🥌'] },
  { name: 'Символы', icon: '❤️', emojis: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💟','☮️','✝️','☪️','🕉️','☸️','✡️','☯️','🛐','⛎','♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓','🔅','🔆','⚠️','♻️','✅','❌','⭕','🛑','⛔','📛','🚫','💯','❗','❕','❓','❔','‼️','⁉️','🔃','🔄','🔙','🔛','🔝','🔚','✔️','🔀','🔁','🔂','▶️','⏩','⏭️','⏯️','◀️','⏪','⏮️'] },
];

const STICKER_PACKS = [
  { name: 'Реакции', stickers: ['😂','🤣','😭','😍','🥰','🤩','😤','🤯','🥳','🎉','💪','👏','🙌','✨','💥','🔥','❤️','💔','😘','🫶','💯','🤦','🤷','🙆','🙅','💁','🤦‍♂️','🤷‍♀️','🫠','😮‍💨'] },
  { name: 'Поддержка', stickers: ['💪','🤝','🫂','🙏','❤️','🫶','🌟','⭐','✨','🎯','🏆','🥇','👑','🌈','🎊','🎉','🎈','💐','🌸','🌺'] },
  { name: 'Грусть/Радость', stickers: ['😢','😭','😿','💧','😊','😁','😄','🎊','🎉','🥳','🤗','😂','🤣','😅','😌','😔','😞','😟','😤','😡'] },
  { name: 'Коты', stickers: ['😺','😸','😹','😻','😼','😽','🙀','😿','😾','🐱','🐈','🐈‍⬛','🐾','🦁','🐯','🦊','🦝','🐻','🐻‍❄️','🐨'] },
];

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SiteConfig {
  primaryColor: string; bgColor: string; fontFamily: string;
  welcomeMessage: string; commands: string[]; logoText: string;
  requireEmailVerification?: boolean; showOnlineStatus?: boolean;
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
  id: string; conversation_id: string; from_id: string; from_name: string;
  from_role: 'user' | 'admin' | 'owner' | 'system';
  text: string | null; media_url: string | null;
  media_type: 'image' | 'video' | 'audio' | 'file' | 'sticker' | null;
  sticker_emoji: string | null; created_at: number; is_read: boolean;
}

interface SiteUser {
  id: string; username: string; email: string | null;
  is_banned: boolean; ban_reason: string | null; last_seen: number; created_at: number;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

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

// ─── Avatar ────────────────────────────────────────────────────────────────────

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

// ─── Emoji Picker ──────────────────────────────────────────────────────────────

const EmojiPicker: React.FC<{ onSelect: (e: string) => void; primary: string }> = ({ onSelect, primary }) => {
  const [cat, setCat] = useState(0);
  return (
    <div className="bg-[#111] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden w-72">
      <div className="flex border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {EMOJI_CATEGORIES.map((c, i) => (
          <button key={i} onClick={() => setCat(i)}
            className="p-2.5 text-base shrink-0 transition-all"
            style={{ background: cat === i ? primary + '20' : 'transparent', opacity: cat === i ? 1 : 0.5 }}>
            {c.icon}
          </button>
        ))}
      </div>
      <div className="p-2 grid grid-cols-8 gap-0.5 max-h-44 overflow-y-auto no-scrollbar">
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

// ─── Sticker Picker ────────────────────────────────────────────────────────────

const StickerPicker: React.FC<{ onSelect: (s: string) => void; primary: string }> = ({ onSelect, primary }) => {
  const [pack, setPack] = useState(0);
  return (
    <div className="bg-[#111] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden w-72">
      <div className="flex border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {STICKER_PACKS.map((p, i) => (
          <button key={i} onClick={() => setPack(i)}
            className="px-3 py-2 text-[9px] font-black uppercase tracking-wider shrink-0 transition-all whitespace-nowrap"
            style={{ color: pack === i ? primary : 'rgba(255,255,255,0.3)', borderBottom: `2px solid ${pack === i ? primary : 'transparent'}` }}>
            {p.name}
          </button>
        ))}
      </div>
      <div className="p-3 grid grid-cols-5 gap-2 max-h-48 overflow-y-auto no-scrollbar">
        {STICKER_PACKS[pack].stickers.map((s, i) => (
          <button key={i} onClick={() => onSelect(s)}
            className="w-12 h-12 flex items-center justify-center text-3xl hover:bg-white/10 rounded-xl transition-all hover:scale-125">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
};

// ─── Message Bubble ────────────────────────────────────────────────────────────

const MessageBubble: React.FC<{ msg: Message; session: ChatSession; primary: string }> = ({ msg, session, primary }) => {
  const isOwn = msg.from_id === session.id;
  const isSystem = msg.from_role === 'system';
  const isAdmin = msg.from_role === 'admin' || msg.from_role === 'owner';

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

  // Стикер
  if (msg.media_type === 'sticker' && msg.sticker_emoji) {
    return (
      <div className={`flex gap-2 mb-2 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
        {!isOwn && <Avatar name={msg.from_name} color={isAdmin ? primary : '#71717a'} />}
        <div className="flex flex-col gap-1" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
          {!isOwn && <span className="text-[9px] font-black uppercase px-1" style={{ color: isAdmin ? primary : 'rgba(255,255,255,0.35)' }}>{msg.from_name}</span>}
          <div className="text-6xl leading-none">{msg.sticker_emoji}</div>
          <span className="text-[9px] px-1" style={{ color: 'rgba(255,255,255,0.25)' }}>{fmtTime(msg.created_at)}</span>
        </div>
      </div>
    );
  }

  // Медиа
  if (msg.media_url) {
    return (
      <div className={`flex gap-2 mb-2 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
        {!isOwn && <Avatar name={msg.from_name} color={isAdmin ? primary : '#71717a'} />}
        <div className="flex flex-col gap-1 max-w-[60%]" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
          {!isOwn && <span className="text-[9px] font-black uppercase px-1" style={{ color: isAdmin ? primary : 'rgba(255,255,255,0.35)' }}>{msg.from_name}</span>}
          <div className="rounded-2xl overflow-hidden border" style={{ borderColor: primary + '20' }}>
            {msg.media_type === 'image' && (
              <img src={msg.media_url} alt="img" className="max-w-xs max-h-64 object-cover cursor-pointer"
                onClick={() => window.open(msg.media_url!, '_blank')} />
            )}
            {msg.media_type === 'video' && (
              <video src={msg.media_url} controls className="max-w-xs max-h-64" />
            )}
            {msg.media_type === 'audio' && (
              <div className="flex items-center gap-3 px-4 py-3 bg-white/5">
                <Play className="w-4 h-4" style={{ color: primary }} />
                <audio src={msg.media_url} controls className="w-48 h-8" />
              </div>
            )}
            {(msg.media_type === 'file' || !msg.media_type) && (
              <a href={msg.media_url} download className="flex items-center gap-3 px-4 py-3 bg-white/5 hover:bg-white/10 transition-all">
                <FileIcon className="w-5 h-5" style={{ color: primary }} />
                <span className="text-xs text-white/70 truncate max-w-[160px]">{msg.media_url.split('/').pop()}</span>
              </a>
            )}
          </div>
          {msg.text && (
            <div className="px-4 py-2.5 rounded-2xl text-sm text-white/90"
              style={{ background: isOwn ? primary : 'rgba(255,255,255,0.07)' }}>
              {msg.text}
            </div>
          )}
          <span className="text-[9px] px-1" style={{ color: 'rgba(255,255,255,0.25)' }}>{fmtTime(msg.created_at)}</span>
        </div>
      </div>
    );
  }

  // Обычное текстовое сообщение
  return (
    <div className={`flex gap-2 mb-2 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isOwn && <Avatar name={msg.from_name} color={isAdmin ? primary : '#71717a'} />}
      <div className="flex flex-col gap-1 max-w-[72%]" style={{ alignItems: isOwn ? 'flex-end' : 'flex-start' }}>
        {!isOwn && (
          <span className="text-[9px] font-black uppercase tracking-wider px-1"
            style={{ color: isAdmin ? primary : 'rgba(255,255,255,0.35)' }}>
            {msg.from_name}
          </span>
        )}
        <div className="px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words"
          style={{
            background: isOwn ? primary : isAdmin ? primary + '18' : 'rgba(255,255,255,0.08)',
            color: '#fff',
            borderRadius: isOwn ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
          }}>
          {msg.text}
        </div>
        <span className="text-[9px] px-1 flex items-center gap-1" style={{ color: 'rgba(255,255,255,0.25)' }}>
          {fmtTime(msg.created_at)}
          {isOwn && <Check className="w-2.5 h-2.5" />}
        </span>
      </div>
    </div>
  );
};

// ─── Message Input ─────────────────────────────────────────────────────────────

const MessageInput: React.FC<{
  onSend: (text: string, mediaUrl?: string, mediaType?: string, sticker?: string) => Promise<void>;
  primary: string; commands: string[]; placeholder?: string;
}> = ({ onSend, primary, commands, placeholder = 'Напишите сообщение...' }) => {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showStickers, setShowStickers] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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
      const { url, media_type } = await r.json();
      await onSend(text.trim() || '', url, media_type);
      setText('');
    } catch { alert('Ошибка загрузки файла'); }
    finally { setUploading(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
    if (e.key === 'Escape') { setShowEmoji(false); setShowStickers(false); setShowCommands(false); }
  };

  return (
    <div className="relative">
      {/* Команды-подсказки */}
      {showCommands && filteredCmds.length > 0 && (
        <div className="absolute bottom-full mb-1 left-0 right-0 bg-[#111] border border-zinc-800 rounded-2xl overflow-hidden shadow-xl">
          {filteredCmds.map(cmd => (
            <button key={cmd} onClick={() => { setText(cmd + ' '); setShowCommands(false); inputRef.current?.focus(); }}
              className="flex items-center gap-2 w-full px-4 py-2.5 hover:bg-white/5 transition-colors text-left text-xs">
              <Hash className="w-3 h-3" style={{ color: primary }} />
              <span className="font-mono" style={{ color: primary }}>{cmd}</span>
            </button>
          ))}
        </div>
      )}

      {/* Emoji попап */}
      {showEmoji && (
        <div className="absolute bottom-full mb-2 left-0 z-10">
          <EmojiPicker onSelect={e => { setText(t => t + e); setShowEmoji(false); inputRef.current?.focus(); }} primary={primary} />
        </div>
      )}

      {/* Sticker попап */}
      {showStickers && (
        <div className="absolute bottom-full mb-2 left-10 z-10">
          <StickerPicker onSelect={doSticker} primary={primary} />
        </div>
      )}

      <input ref={fileRef as any} type="file" className="hidden"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.zip"
        onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />

      <div className="flex gap-2 items-end p-3 border-t" style={{ borderColor: primary + '15' }}>
        {/* Кнопки медиа */}
        <div className="flex gap-1 shrink-0">
          <button onClick={() => { setShowEmoji(v => !v); setShowStickers(false); }}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all text-lg"
            style={{ background: showEmoji ? primary + '30' : 'rgba(255,255,255,0.06)', color: showEmoji ? primary : 'rgba(255,255,255,0.4)' }}>
            😊
          </button>
          <button onClick={() => { setShowStickers(v => !v); setShowEmoji(false); }}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all text-lg"
            style={{ background: showStickers ? primary + '30' : 'rgba(255,255,255,0.06)', color: showStickers ? primary : 'rgba(255,255,255,0.4)' }}>
            🌟
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={uploading}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all disabled:opacity-40"
            style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.4)' }}>
            {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
          </button>
        </div>

        {/* Инпут */}
        <textarea
          ref={inputRef}
          value={text}
          onChange={e => { setText(e.target.value); setShowCommands(e.target.value.startsWith('/')); }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="flex-1 px-4 py-2.5 rounded-2xl text-sm text-white placeholder-white/20 outline-none resize-none overflow-hidden leading-relaxed"
          style={{ background: 'rgba(255,255,255,0.06)', border: `1.5px solid ${primary}25`, maxHeight: '120px', caretColor: primary }}
          onInput={e => { const el = e.target as HTMLTextAreaElement; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }}
        />

        <button onClick={doSend} disabled={!text.trim() || sending}
          className="w-10 h-10 rounded-[14px] flex items-center justify-center transition-all disabled:opacity-30 shrink-0"
          style={{ background: primary, boxShadow: `0 4px 14px ${primary}50` }}>
          {sending ? <RefreshCw className="w-4 h-4 text-white animate-spin" /> : <Send className="w-4 h-4 text-white" />}
        </button>
      </div>
    </div>
  );
};

// ─── Auth Screen ────────────────────────────────────────────────────────────────

const AuthScreen: React.FC<{ site: PublicSite; forceAdmin?: boolean; onAuth: (s: ChatSession) => void }> = ({ site, forceAdmin, onAuth }) => {
  const cfg = site.config;
  const [mode, setMode] = useState<'login' | 'register'>(forceAdmin ? 'login' : 'login');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [verifyCode, setVerifyCode] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState('');

  const p = cfg.primaryColor || '#6366f1';
  const bg = cfg.bgColor || '#09090b';
  const font = cfg.fontFamily || 'Manrope, sans-serif';
  const requireEmail = cfg.requireEmailVerification && mode === 'register';

  const sendCode = async () => {
    if (!email || !email.includes('@')) { setError('Введите корректный email'); return; }
    setLoading(true); setError('');
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/verify-email`, {
        method: 'POST', body: JSON.stringify({ email })
      });
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
      <div className="mb-10 text-center">
        <div className="inline-flex items-center gap-3 mb-2">
          <div className="w-4 h-4 rounded-full" style={{ background: p }} />
          <span className="text-3xl font-black" style={{ color: p }}>{cfg.logoText || site.name}</span>
        </div>
        {!forceAdmin && <p className="text-sm mt-1" style={{ color: p + '70' }}>{cfg.welcomeMessage || 'Чем можем помочь?'}</p>}
        {forceAdmin && <p className="text-xs mt-1 font-bold uppercase tracking-widest" style={{ color: p + '70' }}>Панель администратора</p>}
      </div>

      <div className="w-full max-w-sm rounded-[2.5rem] p-8 backdrop-blur-sm" style={{ background: 'rgba(255,255,255,0.04)', border: `1px solid ${p}25` }}>
        {!forceAdmin && (
          <div className="flex rounded-2xl overflow-hidden border mb-6" style={{ borderColor: p + '20' }}>
            {(['login', 'register'] as const).map(m => (
              <button key={m} onClick={() => { setMode(m); setError(''); }}
                className="flex-1 py-3 text-[10px] font-black uppercase tracking-widest transition-all"
                style={{ background: mode === m ? p : 'transparent', color: mode === m ? '#fff' : p + '70' }}>
                {m === 'login' ? 'Войти' : 'Регистрация'}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: p + '80' }}>
              {mode === 'register' ? 'Имя пользователя' : 'Логин'}
            </label>
            <input value={login} onChange={e => setLogin(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder={mode === 'register' ? 'Никнейм' : 'Введите логин'} autoFocus
              className="w-full bg-white/5 border text-white text-sm p-3.5 rounded-2xl outline-none transition-all placeholder-white/20"
              style={{ borderColor: p + '30' }} />
          </div>

          {mode === 'register' && (
            <div>
              <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: p + '80' }}>Email (опционально)</label>
              <div className="flex gap-2">
                <input value={email} onChange={e => setEmail(e.target.value)} type="email" placeholder="you@example.com"
                  className="flex-1 bg-white/5 border text-white text-sm p-3.5 rounded-2xl outline-none transition-all placeholder-white/20"
                  style={{ borderColor: p + '30' }} />
                {requireEmail && (
                  <button onClick={sendCode} disabled={loading || codeSent}
                    className="px-3 py-2 rounded-2xl text-[9px] font-black uppercase tracking-wider disabled:opacity-40 whitespace-nowrap transition-all"
                    style={{ background: p + '20', color: p, border: `1px solid ${p}30` }}>
                    {codeSent ? '✓ Отправлен' : 'Код'}
                  </button>
                )}
              </div>
            </div>
          )}

          {requireEmail && codeSent && (
            <div>
              <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: p + '80' }}>Код из письма</label>
              <input value={verifyCode} onChange={e => setVerifyCode(e.target.value)} placeholder="123456" maxLength={6}
                className="w-full bg-white/5 border text-white text-sm p-3.5 rounded-2xl outline-none transition-all placeholder-white/20 font-mono tracking-[0.3em] text-center"
                style={{ borderColor: p + '30' }} />
            </div>
          )}

          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-1.5" style={{ color: p + '80' }}>Пароль</label>
            <div className="relative">
              <input type={showPass ? 'text' : 'password'} value={password}
                onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="••••••••"
                className="w-full bg-white/5 border text-white text-sm p-3.5 rounded-2xl outline-none transition-all placeholder-white/20 pr-12"
                style={{ borderColor: p + '30' }} />
              <button onClick={() => setShowPass(v => !v)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors">
                {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span className="text-red-400 text-xs">{error}</span>
            </div>
          )}

          <button onClick={handleSubmit} disabled={loading}
            className="w-full py-4 rounded-2xl font-black text-[11px] uppercase tracking-widest transition-all disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
            style={{ background: p, color: '#fff', boxShadow: `0 8px 24px ${p}40` }}>
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : mode === 'login' ? <ChevronRight className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
            {loading ? 'Подождите...' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Admin Picker ──────────────────────────────────────────────────────────────

const AdminPicker: React.FC<{
  site: PublicSite; session: ChatSession;
  existingConvs: Conversation[]; admins: AdminInfo[];
  onSelect: (conv: Conversation) => void;
  onLogout: () => void;
}> = ({ site, session, existingConvs, admins, onSelect, onLogout }) => {
  const cfg = site.config;
  const p = cfg.primaryColor || '#6366f1';
  const [starting, setStarting] = useState<string | null>(null);

  const startConv = async (adminId: string) => {
    setStarting(adminId);
    try {
      const conv = await apiFetch(`${API}/chat/site/${site.slug}/conversations`, {
        method: 'POST',
        body: JSON.stringify({ user_id: session.id, admin_id: adminId, user_name: session.username })
      });
      onSelect(conv);
    } catch { }
    finally { setStarting(null); }
  };

  const existingConvMap = new Map(existingConvs.map(c => [c.admin_id, c]));

  return (
    <div className="min-h-screen flex flex-col" style={{ background: cfg.bgColor || '#09090b', fontFamily: cfg.fontFamily }}>
      {/* Шапка */}
      <div className="flex items-center justify-between px-6 py-5 border-b" style={{ borderColor: p + '20' }}>
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full" style={{ background: p }} />
          <span className="font-black text-white text-lg">{cfg.logoText || site.name}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold text-white/40">{session.username}</span>
          <button onClick={onLogout} className="p-2 rounded-xl text-white/30 hover:text-white/70 hover:bg-white/5 transition-all">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-2xl mx-auto w-full">
        {/* Приветствие */}
        <div className="mb-8">
          <h2 className="text-2xl font-black text-white mb-1">Привет, {session.username}!</h2>
          <p className="text-white/40 text-sm">{cfg.welcomeMessage || 'Выберите, с кем хотите поговорить'}</p>
        </div>

        {/* Активные диалоги */}
        {existingConvs.length > 0 && (
          <div className="mb-6">
            <p className="text-[9px] font-black uppercase tracking-widest mb-3" style={{ color: p + '80' }}>Ваши диалоги</p>
            <div className="space-y-2">
              {existingConvs.map(conv => {
                const admin = admins.find(a => a.id === conv.admin_id);
                const unread = conv.unread_user || 0;
                return (
                  <button key={conv.id} onClick={() => onSelect(conv)}
                    className="w-full flex items-center gap-4 p-4 rounded-2xl border transition-all text-left hover:scale-[1.01]"
                    style={{ background: 'rgba(255,255,255,0.04)', borderColor: p + '20' }}>
                    <Avatar name={admin?.display_name || conv.admin_name} color={admin?.avatar_color || p} size="w-12 h-12" online={admin?.is_online} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-black text-white text-sm">{admin?.display_name || conv.admin_name}</span>
                        <span className="text-[9px] text-white/30">{conv.last_message_at ? fmtDate(conv.last_message_at) : ''}</span>
                      </div>
                      <p className="text-xs text-white/40 truncate">{conv.last_message_preview || 'Нет сообщений'}</p>
                    </div>
                    {unread > 0 && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black text-white shrink-0"
                        style={{ background: p }}>
                        {unread}
                      </div>
                    )}
                    <ChevronRight className="w-4 h-4 text-white/20 shrink-0" />
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Начать новый диалог */}
        <p className="text-[9px] font-black uppercase tracking-widest mb-3" style={{ color: p + '80' }}>
          {existingConvs.length > 0 ? 'Начать новый диалог с' : 'Выберите специалиста'}
        </p>
        <div className="space-y-3">
          {admins.map(admin => {
            const hasConv = existingConvMap.has(admin.id);
            return (
              <button key={admin.id} onClick={() => startConv(admin.id)} disabled={starting === admin.id}
                className="w-full flex items-center gap-4 p-5 rounded-2xl border transition-all text-left group hover:scale-[1.01] disabled:opacity-60"
                style={{ background: hasConv ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.05)', borderColor: p + '30' }}>
                <Avatar name={admin.display_name} color={admin.avatar_color} size="w-12 h-12" online={admin.is_online} />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-black text-white">{admin.display_name}</span>
                    {admin.is_online && (
                      <span className="text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                        style={{ background: '#10b98120', color: '#10b981' }}>Онлайн</span>
                    )}
                  </div>
                  {admin.bio && <p className="text-xs text-white/40">{admin.bio}</p>}
                </div>
                <div className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all group-hover:scale-110"
                  style={{ background: starting === admin.id ? p + '30' : p }}>
                  {starting === admin.id ? <RefreshCw className="w-3.5 h-3.5 text-white animate-spin" /> : <Plus className="w-3.5 h-3.5 text-white" />}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ─── User Chat View ─────────────────────────────────────────────────────────────

const UserChat: React.FC<{
  site: PublicSite; session: ChatSession;
  conversation: Conversation; admins: AdminInfo[];
  onBack: () => void; onLogout: () => void;
}> = ({ site, session, conversation, admins, onBack, onLogout }) => {
  const cfg = site.config;
  const p = cfg.primaryColor || '#6366f1';
  const [messages, setMessages] = useState<Message[]>([]);
  const [lastTs, setLastTs] = useState(0);
  const [broadcasts, setBroadcasts] = useState<any[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const convId = conversation.id;
  const admin = admins.find(a => a.id === conversation.admin_id);

  const fetchMsgs = useCallback(async (since = lastTs) => {
    try {
      const data: Message[] = await apiFetch(`${API}/chat/site/${site.slug}/conversations/${convId}/messages?since=${since}`);
      if (data.length) {
        setMessages(prev => {
          const ids = new Set(prev.map(m => m.id));
          const fresh = data.filter(m => !ids.has(m.id));
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        setLastTs(Math.max(...data.map(m => m.created_at)));
      }
    } catch { }
  }, [convId, lastTs]);

  useEffect(() => {
    // Initial load
    apiFetch(`${API}/chat/site/${site.slug}/conversations/${convId}/messages?since=0`)
      .then((data: Message[]) => { setMessages(data); if (data.length) setLastTs(Math.max(...data.map(m => m.created_at))); })
      .catch(() => {});
    // Рассылки
    apiFetch(`${API}/chat/site/${site.slug}/broadcasts`).then(setBroadcasts).catch(() => {});
    // Mark read
    fetch(`${API}/chat/site/${site.slug}/conversations/${convId}/read`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ role: 'user' }) });
    const int = setInterval(fetchMsgs, POLL);
    return () => clearInterval(int);
  }, [convId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, broadcasts]);

  const handleSend = async (text: string, mediaUrl?: string, mediaType?: string, sticker?: string) => {
    const r = await apiFetch(`${API}/chat/site/${site.slug}/conversations/${convId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        from_id: session.id, from_name: session.username, from_role: 'user',
        text: text || null, media_url: mediaUrl, media_type: mediaType,
        sticker_emoji: sticker, sticker_type: sticker ? 'sticker' : undefined,
        ...(sticker ? { media_type: 'sticker' } : {})
      })
    });
    setMessages(prev => [...prev, r]);
    setLastTs(r.created_at);
  };

  // Объединяем сообщения и рассылки в хронологическом порядке
  const allItems = [...messages, ...broadcasts.map(b => ({
    ...b, id: b.id, from_role: 'system' as const, from_id: 'system',
    from_name: b.from_name, text: `📢 ${b.text}`, media_url: null, media_type: null, sticker_emoji: null
  }))].sort((a, b) => a.created_at - b.created_at);

  let lastDate = '';

  return (
    <div className="flex flex-col h-screen" style={{ background: cfg.bgColor, fontFamily: cfg.fontFamily }}>
      {/* Шапка */}
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0" style={{ borderColor: p + '20', background: cfg.bgColor + 'ee' }}>
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-white/5 text-white/40 hover:text-white transition-all">
          <ArrowLeft className="w-4 h-4" />
        </button>
        {admin && <Avatar name={admin.display_name} color={admin.avatar_color} size="w-9 h-9" online={admin.is_online} />}
        <div className="flex-1 min-w-0">
          <p className="font-black text-white text-sm truncate">{admin?.display_name || conversation.admin_name}</p>
          <p className="text-[9px] font-bold" style={{ color: p + '80' }}>
            {admin?.is_online ? '● Онлайн' : admin?.bio || ''}
          </p>
        </div>
        <button onClick={onLogout} className="p-2 rounded-xl text-white/20 hover:text-white/50 hover:bg-white/5 transition-all">
          <LogOut className="w-4 h-4" />
        </button>
      </div>

      {/* Сообщения */}
      <div className="flex-1 overflow-y-auto px-4 pt-4 no-scrollbar">
        {allItems.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="text-5xl">👋</div>
            <p className="text-white/30 text-sm font-bold">Напишите первое сообщение</p>
          </div>
        )}
        {allItems.map(msg => {
          const d = fmtDate(msg.created_at);
          const showDate = d !== lastDate;
          if (showDate) lastDate = d;
          return (
            <React.Fragment key={msg.id}>
              {showDate && (
                <div className="flex justify-center my-4">
                  <span className="text-[9px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full"
                    style={{ color: p + '70', background: p + '12' }}>{d}</span>
                </div>
              )}
              <MessageBubble msg={msg as Message} session={session} primary={p} />
            </React.Fragment>
          );
        })}
        <div ref={bottomRef} className="h-2" />
      </div>

      <MessageInput onSend={handleSend} primary={p} commands={cfg.commands || []} />
    </div>
  );
};

// ─── Admin Chat Panel ───────────────────────────────────────────────────────────

const AdminChatPanel: React.FC<{
  site: PublicSite; session: ChatSession;
  onLogout: () => void;
}> = ({ site, session, onLogout }) => {
  const cfg = site.config;
  const p = cfg.primaryColor || '#6366f1';
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [users, setUsers] = useState<SiteUser[]>([]);
  const [tab, setTab] = useState<'chat' | 'users' | 'broadcast'>('chat');
  const [lastTs, setLastTs] = useState(0);
  const [broadcastText, setBroadcastText] = useState('');
  const [sending, setSending] = useState(false);
  const [banReason, setBanReason] = useState('');
  const [showBanModal, setShowBanModal] = useState<SiteUser | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const isAdminRole = session.role === 'admin' || session.role === 'owner';

  const fetchConvs = async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/conversations?role=${session.role}&session_id=${session.id}`);
      setConvs(Array.isArray(data) ? data : []);
    } catch { }
  };

  const fetchMessages = useCallback(async (convId: string, since = 0) => {
    try {
      const data: Message[] = await apiFetch(`${API}/chat/site/${site.slug}/conversations/${convId}/messages?since=${since}`);
      if (data.length) {
        setMessages(prev => {
          const ids = new Set(prev.map(m => m.id));
          const fresh = data.filter(m => !ids.has(m.id));
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        setLastTs(Math.max(...data.map(m => m.created_at)));
      }
    } catch { }
  }, []);

  useEffect(() => {
    fetchConvs();
    // Обновляем статус онлайн
    if (session.role === 'admin') {
      fetch(`${API}/chat/sites/${site.id}/admins/${session.id}/online`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ is_online: true })
      });
    }
    if (tab === 'users') {
      apiFetch(`${API}/chat/site/${site.slug}/users?role=${session.role}`).then(setUsers).catch(() => {});
    }
  }, [tab]);

  useEffect(() => {
    const convInt = setInterval(fetchConvs, POLL);
    return () => {
      convInt;
      clearInterval(convInt);
      if (session.role === 'admin') {
        fetch(`${API}/chat/sites/${site.id}/admins/${session.id}/online`, {
          method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ is_online: false })
        });
      }
    };
  }, []);

  useEffect(() => {
    if (!selectedConv) return;
    setMessages([]);
    apiFetch(`${API}/chat/site/${site.slug}/conversations/${selectedConv.id}/messages?since=0`)
      .then((data: Message[]) => { setMessages(data); if (data.length) setLastTs(Math.max(...data.map(m => m.created_at))); })
      .catch(() => {});
    fetch(`${API}/chat/site/${site.slug}/conversations/${selectedConv.id}/read`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ role: session.role })
    });
    const int = setInterval(() => fetchMessages(selectedConv.id, lastTs), POLL);
    return () => clearInterval(int);
  }, [selectedConv?.id]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async (text: string, mediaUrl?: string, mediaType?: string, sticker?: string) => {
    if (!selectedConv) return;
    const r = await apiFetch(`${API}/chat/site/${site.slug}/conversations/${selectedConv.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        from_id: session.id, from_name: session.display_name || session.username,
        from_role: session.role, text: text || null,
        media_url: mediaUrl, media_type: sticker ? 'sticker' : mediaType,
        sticker_emoji: sticker
      })
    });
    setMessages(prev => [...prev, r]);
    setLastTs(r.created_at);
    fetchConvs();
  };

  const handleBan = async (u: SiteUser, isBanned: boolean, reason = '') => {
    await fetch(`${API}/chat/site/${site.slug}/users/${u.id}/ban`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ role: session.role, is_banned: isBanned, ban_reason: reason })
    });
    setUsers(prev => prev.map(usr => usr.id === u.id ? { ...usr, is_banned: isBanned, ban_reason: reason } : usr));
    setShowBanModal(null);
  };

  const handleBroadcast = async () => {
    if (!broadcastText.trim() || sending) return;
    setSending(true);
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ role: session.role, from_id: session.id, from_name: session.display_name || session.username, text: broadcastText })
      });
      setBroadcastText('');
    } catch { } finally { setSending(false); }
  };

  const totalUnread = convs.reduce((acc, c) => acc + (c.unread_admin || 0), 0);
  const TABS = [
    { id: 'chat', label: 'Диалоги', icon: MessageCircle, badge: totalUnread },
  ] as const;

  return (
    <div className="flex h-screen" style={{ background: cfg.bgColor, fontFamily: cfg.fontFamily }}>
      {/* Ban Modal */}
      {showBanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70" onClick={() => setShowBanModal(null)} />
          <div className="relative bg-[#111] border border-zinc-800 rounded-[2rem] p-6 w-80">
            <h3 className="text-white font-black mb-4">Заблокировать {showBanModal.username}?</h3>
            <textarea value={banReason} onChange={e => setBanReason(e.target.value)} placeholder="Причина (необязательно)"
              rows={3} className="w-full bg-black border border-zinc-800 text-white text-sm p-3 rounded-xl outline-none resize-none mb-4" />
            <div className="flex gap-3">
              <button onClick={() => setShowBanModal(null)} className="flex-1 py-3 rounded-2xl bg-zinc-800 text-white text-xs font-bold">Отмена</button>
              <button onClick={() => handleBan(showBanModal, true, banReason)} className="flex-1 py-3 rounded-2xl bg-rose-600 text-white text-xs font-bold">Заблокировать</button>
            </div>
          </div>
        </div>
      )}

      {/* Сайдбар */}
      <div className="w-72 border-r flex flex-col shrink-0" style={{ borderColor: p + '20', background: cfg.bgColor + 'dd' }}>
        <div className="p-5 border-b" style={{ borderColor: p + '15' }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: p }} />
            <span className="font-black text-white">{cfg.logoText || site.name}</span>
          </div>
          <div className="flex items-center gap-2">
            <Shield className="w-3 h-3" style={{ color: p }} />
            <span className="text-[10px] font-black uppercase tracking-wider" style={{ color: p }}>
              {session.role === 'owner' ? 'Владелец' : session.display_name || session.username}
            </span>
          </div>
        </div>

        <nav className="p-2 space-y-0.5">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id as any)}
              className="flex items-center gap-3 w-full px-4 py-3 rounded-2xl transition-all text-left"
              style={{ background: tab === t.id ? p + '20' : 'transparent', color: tab === t.id ? p : 'rgba(255,255,255,0.4)' }}>
              <t.icon className="w-4 h-4 shrink-0" />
              <span className="text-xs font-bold">{t.label}</span>
              {(t as any).badge > 0 && (
                <span className="ml-auto text-[8px] font-black px-2 py-0.5 rounded-full text-white" style={{ background: p }}>
                  {(t as any).badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Список диалогов */}
        {tab === 'chat' && (
          <div className="flex-1 overflow-y-auto p-2 no-scrollbar">
            {convs.length === 0 ? (
              <div className="text-center py-8">
                <MessageCircle className="w-8 h-8 mx-auto mb-2" style={{ color: p + '30' }} />
                <p className="text-[10px] text-white/20 font-bold">Нет диалогов</p>
              </div>
            ) : (
              <div className="space-y-1">
                {convs.map(conv => {
                  const unread = conv.unread_admin || 0;
                  const isSelected = selectedConv?.id === conv.id;
                  return (
                    <button key={conv.id} onClick={() => setSelectedConv(conv)}
                      className="w-full flex items-start gap-3 p-3 rounded-2xl transition-all text-left"
                      style={{ background: isSelected ? p + '20' : 'rgba(255,255,255,0.03)', border: `1px solid ${isSelected ? p + '40' : 'transparent'}` }}>
                      <Avatar name={conv.user_name || '?'} size="w-8 h-8" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-black text-white truncate">{conv.user_name}</span>
                          {unread > 0 && (
                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded-full text-white shrink-0 ml-1" style={{ background: p }}>
                              {unread}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-white/30 truncate mt-0.5">{conv.last_message_preview || '...'}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div className="p-3 border-t mt-auto" style={{ borderColor: p + '10' }}>
          <button onClick={onLogout} className="flex items-center gap-2 w-full px-4 py-2.5 rounded-2xl text-[9px] font-black uppercase tracking-wider text-white/30 hover:text-white/60 hover:bg-white/5 transition-all">
            <LogOut className="w-3.5 h-3.5" /> Выйти
          </button>
        </div>
      </div>

      {/* Основная область */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── Чат ── */}
        {tab === 'chat' && (
          <>
            {!selectedConv ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <MessageCircle className="w-12 h-12 mx-auto mb-3" style={{ color: p + '30' }} />
                  <p className="text-white/30 font-bold">Выберите диалог</p>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: p + '15' }}>
                  <div className="flex items-center gap-3">
                    <Avatar name={selectedConv.user_name || '?'} size="w-9 h-9" />
                    <div>
                      <p className="font-black text-white">{selectedConv.user_name}</p>
                      <p className="text-[9px] font-bold text-white/30">пользователь</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {tab === 'chat' && selectedConv && (() => {
                      const u = users.find(u => u.id === selectedConv.user_id);
                      return u ? (
                        u.is_banned ? (
                          <button onClick={() => handleBan(u, false)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <Ban className="w-3 h-3" /> Разблокировать
                          </button>
                        ) : (
                          <button onClick={() => { setBanReason(''); setShowBanModal(u); }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-wider bg-rose-500/10 text-rose-400 border border-rose-500/20">
                            <Ban className="w-3 h-3" /> Заблокировать
                          </button>
                        )
                      ) : null;
                    })()}
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto px-5 pt-4 no-scrollbar">
                  {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full gap-2">
                      <MessageCircle className="w-8 h-8" style={{ color: p + '30' }} />
                      <p className="text-white/20 text-sm">Нет сообщений</p>
                    </div>
                  )}
                  {messages.map(msg => (
                    <MessageBubble key={msg.id} msg={msg} session={session} primary={p} />
                  ))}
                  <div ref={bottomRef} className="h-2" />
                </div>

                <MessageInput onSend={handleSend} primary={p} commands={[]} placeholder={`Ответить ${selectedConv.user_name}...`} />
              </>
            )}
          </>
        )}

        {/* ── Пользователи ── */}
        {tab === 'users' && (
          <div className="flex-1 overflow-y-auto p-6">
            <h2 className="text-xl font-black text-white mb-5">Пользователи ({users.length})</h2>
            <div className="space-y-2">
              {users.map(u => (
                <div key={u.id} className="flex items-center gap-4 p-4 rounded-2xl border transition-all"
                  style={{ background: 'rgba(255,255,255,0.03)', borderColor: p + '15' }}>
                  <Avatar name={u.username} size="w-10 h-10" />
                  <div className="flex-1 min-w-0">
                    <p className={`font-bold text-sm ${u.is_banned ? 'text-white/30 line-through' : 'text-white'}`}>{u.username}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      {u.email && <span className="text-[9px] text-white/30 flex items-center gap-1"><Mail className="w-2.5 h-2.5" />{u.email}</span>}
                      <span className="text-[9px] text-white/20">Был: {u.last_seen ? new Date(u.last_seen).toLocaleDateString('ru') : '—'}</span>
                    </div>
                    {u.is_banned && u.ban_reason && <p className="text-[9px] text-rose-400 mt-0.5">Причина: {u.ban_reason}</p>}
                  </div>
                  {u.is_banned ? (
                    <button onClick={() => handleBan(u, false)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 transition-all">
                      <Check className="w-3 h-3" /> Разблок
                    </button>
                  ) : (
                    <button onClick={() => { setBanReason(''); setShowBanModal(u); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-wider bg-rose-500/10 text-rose-400 border border-rose-500/20 transition-all">
                      <Ban className="w-3 h-3" /> Бан
                    </button>
                  )}
                </div>
              ))}
              {users.length === 0 && (
                <div className="text-center py-16">
                  <Users className="w-10 h-10 text-white/10 mx-auto mb-3" />
                  <p className="text-white/30 font-bold">Нет пользователей</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Рассылка ── */}
        {tab === 'broadcast' && (
          <div className="flex-1 p-6">
            <h2 className="text-xl font-black text-white mb-5">Рассылка</h2>
            <div className="max-w-2xl">
              <div className="p-5 rounded-[1.5rem] border mb-4" style={{ background: 'rgba(255,255,255,0.03)', borderColor: p + '20' }}>
                <p className="text-[9px] font-black uppercase tracking-wider mb-3" style={{ color: p }}>Сообщение всем пользователям</p>
                <textarea value={broadcastText} onChange={e => setBroadcastText(e.target.value)}
                  placeholder="Текст сообщения..." rows={5}
                  className="w-full bg-transparent text-white text-sm outline-none resize-none placeholder-white/20 leading-relaxed" />
              </div>
              <button onClick={handleBroadcast} disabled={!broadcastText.trim() || sending}
                className="flex items-center gap-2 px-8 py-4 rounded-2xl font-black text-[10px] uppercase tracking-wider disabled:opacity-40 transition-all"
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

// ─── Root ──────────────────────────────────────────────────────────────────────

const ChatSiteApp: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [sp] = useSearchParams();
  const forceAdmin = sp.get('as') === 'admin';

  const [site, setSite] = useState<PublicSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<ChatSession | null>(() => {
    try { const s = localStorage.getItem(`cs_session_${slug}`); return s ? JSON.parse(s) : null; } catch { return null; }
  });
  const [admins, setAdmins] = useState<AdminInfo[]>([]);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);

  useEffect(() => {
    apiFetch(`${API}/chat/site/${slug}/public`)
      .then(setSite).catch(() => setSite(null))
      .finally(() => setLoading(false));
    apiFetch(`${API}/chat/site/${slug}/admins`).then(setAdmins).catch(() => {});
  }, [slug]);

  useEffect(() => {
    if (!session || !site) return;
    if (session.role === 'user') {
      apiFetch(`${API}/chat/site/${slug}/conversations?role=user&session_id=${session.id}`)
        .then(setConvs).catch(() => {});
    }
  }, [session?.id, site]);

  const handleAuth = (s: ChatSession) => {
    setSession(s);
    localStorage.setItem(`cs_session_${slug}`, JSON.stringify(s));
  };

  const handleLogout = () => {
    if (session?.role === 'admin') {
      fetch(`${API}/chat/sites/${site?.id}/admins/${session.id}/online`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ is_online: false })
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

  if (!session) return <AuthScreen site={site} forceAdmin={forceAdmin} onAuth={handleAuth} />;

  if (session.role === 'admin' || session.role === 'owner') {
    return <AdminChatPanel site={site} session={session} onLogout={handleLogout} />;
  }

  // User: если выбран диалог — показываем чат, иначе выбор администратора
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

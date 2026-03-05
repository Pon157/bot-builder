import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Zap, BarChart2, MessageSquare, ShieldCheck,
  Settings, Play, Square, Loader2, AlertTriangle,
  Crown, Plus, Trash2, Save, ArrowLeft,
  Info, Wifi, WifiOff, User, Image, Send, ShieldAlert,
  CheckSquare, Square as SquareIcon, Lock, ToggleLeft, ToggleRight,
  Users, Hash, Eye, EyeOff, Upload, RefreshCw, Link, Type,
  ChevronDown, ChevronUp, ExternalLink, Copy, CheckCheck
} from 'lucide-react';

const FREE_API  = (path: string) => `/api/free${path}`;
const BOTS_API  = (path: string) => `/api${path}`;

// ─── types ────────────────────────────────────────────────────────────────────
interface FreeBot {
  id: string;
  name: string;
  status: string;
  token?: string;
  config?: any;
  is_free_plan: boolean;
  memory_limit_mb: number;
  ad_enabled: boolean;
  platform?: 'telegram' | 'vk';
}

interface AccountInfo {
  id: string; email: string; username: string; plan: string;
  linked_pro_user_id?: string;
  pro_account?: { id: string; email: string; username: string; balance: number; license_expires_at?: number; };
}

interface InlineButton {
  id: string;
  text: string;
  type: 'url' | 'message';
  value: string;
}

// ─── Token Guide Component ────────────────────────────────────────────────────
const TelegramTokenGuide: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const CopyBtn: React.FC<{ text: string; id: string }> = ({ text, id }) => (
    <button
      type="button"
      onClick={() => copy(text, id)}
      className="inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px] text-zinc-400 hover:text-white transition-all font-mono ml-2"
    >
      {copied === id ? <CheckCheck size={10} className="text-green-400" /> : <Copy size={10} />}
      <span className="font-mono">{text}</span>
    </button>
  );

  return (
    <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-blue-500/5 transition-colors"
      >
        <span className="text-base">🤖</span>
        <div className="flex-1">
          <p className="text-xs font-bold text-blue-300">Как получить Telegram Bot Token?</p>
          <p className="text-[10px] text-zinc-500">Пошаговый гайд · ~2 минуты</p>
        </div>
        {open ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-blue-500/10">
          <div className="mt-3 space-y-3">

            {/* Step 1 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">1</div>
              <div>
                <p className="text-xs font-bold text-white">Откройте @BotFather в Telegram</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Найдите бота <span className="text-blue-300 font-mono">@BotFather</span> в поиске Telegram или перейдите по ссылке:
                </p>
                <a
                  href="https://t.me/BotFather"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 mt-1.5 px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 rounded-lg text-[11px] text-blue-300 font-bold transition-colors"
                >
                  <ExternalLink size={11} /> Открыть @BotFather
                </a>
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">2</div>
              <div>
                <p className="text-xs font-bold text-white">Создайте нового бота</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Отправьте команду <CopyBtn text="/newbot" id="newbot" /> и следуйте инструкциям:
                </p>
                <div className="mt-2 bg-zinc-900 rounded-lg p-3 space-y-1.5 border border-zinc-800">
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-zinc-600 font-mono mt-0.5 flex-shrink-0">BotFather:</span>
                    <span className="text-[11px] text-zinc-300">Alright, a new bot. How are we going to call it? Please choose a name for your bot.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-blue-500 font-mono mt-0.5 flex-shrink-0">Вы:</span>
                    <span className="text-[11px] text-zinc-400 italic">Введите любое название, например: Мой Магазин</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-zinc-600 font-mono mt-0.5 flex-shrink-0">BotFather:</span>
                    <span className="text-[11px] text-zinc-300">Good. Now let's choose a username for your bot. It must end in `bot`.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-blue-500 font-mono mt-0.5 flex-shrink-0">Вы:</span>
                    <span className="text-[11px] text-zinc-400 italic">Введите username, оканчивающийся на _bot, например: myshop_bot</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-green-600 flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">3</div>
              <div>
                <p className="text-xs font-bold text-white">Скопируйте токен</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  BotFather пришлёт сообщение с токеном — длинную строку вида:
                </p>
                <div className="mt-2 bg-zinc-950 rounded-lg p-2.5 border border-zinc-800 font-mono text-[11px] text-green-400 break-all">
                  1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
                </div>
                <p className="text-[10px] text-zinc-500 mt-1.5">⚠️ Не передавайте токен никому — он даёт полный контроль над ботом</p>
              </div>
            </div>

            {/* Admin chat tip */}
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3">
              <p className="text-[11px] font-bold text-amber-300 mb-1">💡 Как получить ID группы-администратора?</p>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Добавьте бота в группу/форум, потом отправьте команду <span className="font-mono text-white bg-zinc-800 px-1 rounded">/getid</span> прямо в эту группу — бот ответит её ID.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const VKTokenGuide: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="rounded-xl border border-blue-400/20 bg-[#4680C2]/5 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-[#4680C2]/5 transition-colors"
      >
        <span className="text-base">🔵</span>
        <div className="flex-1">
          <p className="text-xs font-bold text-[#7ab3f0]">Как получить VK Community Token?</p>
          <p className="text-[10px] text-zinc-500">Пошаговый гайд · ~3 минуты</p>
        </div>
        {open ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-[#4680C2]/10">
          <div className="mt-3 space-y-3">

            {/* Step 1 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-[#4680C2] flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">1</div>
              <div>
                <p className="text-xs font-bold text-white">Создайте сообщество ВКонтакте</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Перейдите в раздел «Сообщества» → «Создать сообщество» (или используйте уже имеющееся).
                  Подойдёт любой тип: группа, паблик, мероприятие.
                </p>
                <a
                  href="https://vk.com/groups"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 mt-1.5 px-3 py-1.5 bg-[#4680C2]/20 hover:bg-[#4680C2]/30 border border-[#4680C2]/30 rounded-lg text-[11px] text-[#7ab3f0] font-bold transition-colors"
                >
                  <ExternalLink size={11} /> Мои сообщества ВК
                </a>
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-[#4680C2] flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">2</div>
              <div>
                <p className="text-xs font-bold text-white">Зайдите в настройки сообщества</p>
                <div className="mt-2 bg-zinc-900 rounded-lg p-3 border border-zinc-800 space-y-1">
                  {[
                    'Откройте страницу своего сообщества',
                    'Нажмите «Управление» (кнопка под обложкой)',
                    'В меню слева выберите «Настройки»',
                    'Перейдите на вкладку «Работа с API»',
                  ].map((s, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-[10px] text-zinc-600 mt-0.5 flex-shrink-0">{i + 1}.</span>
                      <span className="text-[11px] text-zinc-300">{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-[#4680C2] flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">3</div>
              <div>
                <p className="text-xs font-bold text-white">Создайте ключ доступа</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  На вкладке «Работа с API» нажмите <span className="text-white font-bold">«Создать ключ»</span>.
                  Выберите необходимые права доступа:
                </p>
                <div className="mt-2 space-y-1">
                  {[
                    { label: 'Управление сообществом', required: true },
                    { label: 'Сообщения сообщества', required: true },
                    { label: 'Документы', required: false },
                    { label: 'Фотографии', required: true },
                  ].map(p => (
                    <div key={p.label} className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold ${p.required ? 'text-green-400' : 'text-zinc-600'}`}>
                        {p.required ? '✓' : '○'}
                      </span>
                      <span className={`text-[11px] ${p.required ? 'text-white' : 'text-zinc-500'}`}>{p.label}</span>
                      {p.required && <span className="text-[9px] bg-green-500/10 text-green-400 px-1.5 rounded-full font-bold uppercase">нужно</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Step 4 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-[#4680C2] flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">4</div>
              <div>
                <p className="text-xs font-bold text-white">Включите Long Poll API</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  В том же разделе «Работа с API» перейдите на вкладку <span className="text-white font-bold">«Long Poll API»</span>:
                </p>
                <div className="mt-2 bg-zinc-900 rounded-lg p-3 border border-zinc-800 space-y-1">
                  {[
                    'Включите Long Poll API (переключатель)',
                    'Версия API: выберите последнюю (5.131 или выше)',
                    'В разделе «Типы событий» включите: Входящие сообщения',
                  ].map((s, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-[10px] text-zinc-600 mt-0.5 flex-shrink-0">{i + 1}.</span>
                      <span className="text-[11px] text-zinc-300">{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Step 5 */}
            <div className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-green-600 flex items-center justify-center text-[10px] font-black text-white flex-shrink-0 mt-0.5">5</div>
              <div>
                <p className="text-xs font-bold text-white">Скопируйте токен</p>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Вернитесь на вкладку «Ключи доступа» и скопируйте созданный ключ — длинная строка вида:
                </p>
                <div className="mt-2 bg-zinc-950 rounded-lg p-2.5 border border-zinc-800 font-mono text-[11px] text-green-400 break-all">
                  vk1.a.Abc123...XyzLongTokenString
                </div>
                <p className="text-[10px] text-zinc-500 mt-1.5">⚠️ Токен даёт доступ к сообществу — не передавайте его третьим лицам</p>
              </div>
            </div>

            {/* Admin chat tip */}
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3">
              <p className="text-[11px] font-bold text-amber-300 mb-1">💡 Как указать беседу-администратора?</p>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Добавьте бота (сообщество) в беседу ВКонтакте — он автоматически привяжется к ней и сообщит её peer_id.
                Либо оставьте поле пустым: привязка произойдёт при первом добавлении в беседу.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Account Badge ────────────────────────────────────────────────────────────
const AccountBadge: React.FC<{ userId: string }> = ({ userId }) => {
  const [info, setInfo] = useState<AccountInfo | null>(null);
  useEffect(() => {
    fetch(FREE_API(`/user-info/${userId}`))
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setInfo(d))
      .catch(() => {});
  }, [userId]);
  if (!info) return null;
  const isPro = !!info.pro_account;
  return (
    <div className="fixed top-4 right-4 z-50 group">
      <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-bold transition-all cursor-default ${isPro ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-zinc-900 border-zinc-700 text-zinc-400'}`}>
        <div className={`w-1.5 h-1.5 rounded-full ${isPro ? 'bg-amber-400' : 'bg-zinc-500'}`} />
        <User size={11} />
        <span className="uppercase tracking-wider">{isPro ? '⭐ PRO' : 'FREE'}</span>
        <span className="text-zinc-600 hidden group-hover:inline">· {info.email?.split('@')[0]}</span>
      </div>
      <div className="absolute top-full right-0 mt-1 w-56 bg-zinc-900 border border-zinc-800 rounded-xl p-3 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-xl">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Аккаунт</div>
        <div className="text-white text-xs font-bold truncate">{info.email}</div>
        {info.pro_account && (
          <>
            <div className="mt-1 text-[10px] text-zinc-500">Привязан к Pro:</div>
            <div className="text-amber-400 text-xs font-bold truncate">{info.pro_account.email}</div>
            <div className="text-zinc-500 text-[10px] mt-1">Баланс: {info.pro_account.balance?.toFixed(2)} ₽</div>
          </>
        )}
        <div className={`mt-2 text-[10px] font-bold uppercase px-2 py-1 rounded-lg inline-block ${isPro ? 'bg-amber-500/20 text-amber-400' : 'bg-zinc-800 text-zinc-500'}`}>
          {isPro ? 'Pro Plan' : 'Free Plan'}
        </div>
      </div>
    </div>
  );
};

// ─── Toggle ────────────────────────────────────────────────────────────────────
const Toggle: React.FC<{
  value: boolean;
  onChange: (v: boolean) => void;
  label: string;
  sub?: string;
  color?: string;
}> = ({ value, onChange, label, sub, color = 'blue' }) => {
  const colors: Record<string, string> = {
    blue:    'bg-blue-500/10 border-blue-500/30 text-blue-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    amber:   'bg-amber-500/10 border-amber-500/30 text-amber-400',
    zinc:    'bg-zinc-800 border-zinc-700 text-white',
  };
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`w-full flex items-center justify-between p-4 rounded-xl border transition-all text-left ${value ? (colors[color] || colors.blue) : 'bg-black border-zinc-800 text-zinc-600'}`}
    >
      <div>
        <p className="text-xs font-bold">{label}</p>
        {sub && <p className="text-[9px] uppercase opacity-60 mt-0.5">{sub}</p>}
      </div>
      {value ? <ToggleRight className="w-5 h-5 flex-shrink-0" /> : <ToggleLeft className="w-5 h-5 flex-shrink-0" />}
    </button>
  );
};

// ─── Section ────────────────────────────────────────────────────────────────────
const Section: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode }> = ({ title, icon, children }) => (
  <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-5 space-y-4">
    <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest flex items-center gap-2">{icon}{title}</h2>
    {children}
  </section>
);

// ════════════════════════════════════════════════════════════════════════════════
// FREE BOT EDITOR — Telegram
// ════════════════════════════════════════════════════════════════════════════════
const FreeBotEditor: React.FC<{
  bot: FreeBot;
  userId: string;
  onSave: (updated: FreeBot) => void;
  onBack: () => void;
}> = ({ bot, userId, onSave, onBack }) => {

  const initState = useCallback((b: FreeBot) => {
    const cfg         = b.config || {};
    const rawSettings = cfg.settings || {};
    const defaultSettings = {
      useTopics: false, topicPerRequest: false, anonymousTopics: false,
      forwardAll: false, forwardMessages: false, rateLimit: 1, autoBanThreshold: 3,
      showHeaderId: true, showHeaderName: true, showHeaderUsername: true,
      firstMessageHeader: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>',
      ticketMessageHeader: '🆘 <b>ЗАЯВКА [{btn}]:</b>',
      commonMessageHeader: '📩 <b>СООБЩЕНИЕ:</b>',
    };
    return {
      name:         b.name,
      token:        b.token || cfg.token || '',
      welcome:      cfg.welcomeMessage || '',
      welcomePhoto: cfg.welcomePhoto   || '',
      adminId:      cfg.adminChatId    || '',
      buttons:      (cfg.buttons  || []) as any[],
      triggers:     (cfg.triggers || []) as any[],
      inlineButtons:(cfg.inlineButtons || []) as InlineButton[],
      stg:          { ...defaultSettings, ...rawSettings },
    };
  }, []);

  const [name,          setName]          = useState(() => initState(bot).name);
  const [token,         setToken]         = useState(() => initState(bot).token);
  const [welcome,       setWelcome]       = useState(() => initState(bot).welcome);
  const [welcomePhoto,  setWelcomePhoto]  = useState(() => initState(bot).welcomePhoto);
  const [adminId,       setAdminId]       = useState(() => initState(bot).adminId);
  const [buttons,       setButtons]       = useState<any[]>(() => initState(bot).buttons);
  const [triggers,      setTriggers]      = useState<any[]>(() => initState(bot).triggers);
  const [inlineButtons, setInlineButtons] = useState<InlineButton[]>(() => initState(bot).inlineButtons);
  const [stg,           setStg]           = useState(() => initState(bot).stg);
  const [showToken,     setShowToken]     = useState(false);
  const [saving,        setSaving]        = useState(false);
  const [saveSuccess,   setSaveSuccess]   = useState(false);
  const [error,         setError]         = useState('');
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  const prevBotIdRef = useRef(bot.id);
  useEffect(() => {
    if (prevBotIdRef.current !== bot.id) {
      prevBotIdRef.current = bot.id;
      const s = initState(bot);
      setName(s.name); setToken(s.token); setWelcome(s.welcome);
      setWelcomePhoto(s.welcomePhoto); setAdminId(s.adminId);
      setButtons(s.buttons); setTriggers(s.triggers);
      setInlineButtons(s.inlineButtons); setStg(s.stg);
      setError(''); setSaveSuccess(false);
    }
  }, [bot.id, initState]);

  const updateStg = useCallback((key: string, val: any) => {
    setStg(prev => ({ ...prev, [key]: val }));
  }, []);

  const handlePhotoFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setUploadingPhoto(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/upload', { method: 'POST', body: fd });
      if (!r.ok) {
        const errData = await r.json().catch(() => ({}));
        throw new Error(errData.detail || `Ошибка загрузки (${r.status})`);
      }
      const d = await r.json();
      const url = d.url || d.path || '';
      if (!url) throw new Error('Сервер не вернул URL файла');
      setWelcomePhoto(url);
    } catch (err: any) {
      setError(err.message || 'Ошибка загрузки фото');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true); setError(''); setSaveSuccess(false);
    try {
      const payload = {
        user_id: userId, name, token: token.trim() || undefined,
        buttons, triggers,
        config: {
          welcomeMessage: welcome, welcomePhoto: welcomePhoto,
          adminChatId: adminId, inlineButtons, settings: stg,
        },
      };
      const res = await fetch(FREE_API(`/bots/${bot.id}/config`), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Ошибка сохранения (${res.status})`);
      }
      let serverBot: any = null;
      try { serverBot = await res.json(); } catch {}
      const updatedBot: FreeBot = {
        ...bot, name,
        token: serverBot?.token || token.trim() || bot.token,
        config: { ...(bot.config || {}), welcomeMessage: welcome, welcomePhoto, adminChatId: adminId, inlineButtons, settings: stg, buttons, triggers },
      };
      onSave(updatedBot);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e: any) {
      setError(e.message || 'Неизвестная ошибка');
    } finally {
      setSaving(false);
    }
  };

  const addButton    = useCallback(() => setButtons(prev => [...prev, { id: `btn_${Date.now()}`, text: '', type: 'default', response: '' }]), []);
  const removeButton = useCallback((idx: number) => setButtons(prev => prev.filter((_, i) => i !== idx)), []);
  const updateButton = useCallback((idx: number, field: string, val: string) => setButtons(prev => prev.map((b, i) => i === idx ? { ...b, [field]: val } : b)), []);

  const addTrigger    = useCallback(() => setTriggers(prev => [...prev, { id: `trg_${Date.now()}`, keyword: '', response: '' }]), []);
  const removeTrigger = useCallback((idx: number) => setTriggers(prev => prev.filter((_, i) => i !== idx)), []);
  const updateTrigger = useCallback((idx: number, field: string, val: string) => setTriggers(prev => prev.map((t, i) => i === idx ? { ...t, [field]: val } : t)), []);

  const addInlineButton    = useCallback(() => setInlineButtons(prev => [...prev, { id: `inl_${Date.now()}`, text: '', type: 'url', value: '' }]), []);
  const removeInlineButton = useCallback((idx: number) => setInlineButtons(prev => prev.filter((_, i) => i !== idx)), []);
  const updateInlineButton = useCallback((idx: number, field: keyof InlineButton, val: string) => setInlineButtons(prev => prev.map((b, i) => i === idx ? { ...b, [field]: val } : b)), []);

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-2xl mx-auto p-6 md:p-10 space-y-5 pb-24">
        <div className="flex items-center gap-4 mb-2">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="px-2 py-0.5 bg-zinc-800 rounded-full text-[10px] text-zinc-400 font-bold uppercase tracking-widest">Free · Telegram</span>
              {bot.ad_enabled && <span className="px-2 py-0.5 bg-amber-500/10 rounded-full text-[10px] text-amber-400 font-bold uppercase tracking-widest">📢 Реклама</span>}
            </div>
          </div>
        </div>

        <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-4 flex items-center gap-3">
          <span className="text-amber-400 text-lg">📢</span>
          <p className="text-[11px] text-zinc-400 leading-relaxed">
            На free-плане после /start автоматически показывается реклама. Переходите на Pro для отключения рекламы и разблокировки всех функций.
          </p>
        </div>

        {/* Гайд по токену прямо в редакторе */}
        <TelegramTokenGuide />

        <Section title="Основные настройки" icon={<Settings size={13} className="text-blue-400" />}>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Название бота</span>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="Мой бот" />
          </label>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Telegram Bot Token</span>
            <div className="relative">
              <input type={showToken ? 'text' : 'password'} value={token} onChange={e => setToken(e.target.value)}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 pr-10 text-sm text-white font-mono focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="Токен от @BotFather" />
              <button type="button" onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors">
                {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </label>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5">
              <Users size={10} className="text-amber-400" />ID группы / форума администраторов
            </span>
            <input value={adminId} onChange={e => setAdminId(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500 transition-colors"
              placeholder="-100123456789" />
          </label>
        </Section>

        <Section title="Приветствие (/start)" icon={<MessageSquare size={13} className="text-emerald-400" />}>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Текст приветствия</span>
            <textarea value={welcome} onChange={e => setWelcome(e.target.value)} rows={3}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors resize-none"
              placeholder="Добро пожаловать!" />
            <p className="text-[10px] text-amber-500/70 mt-1.5">ℹ️ На free-плане после приветствия автоматически показывается реклама</p>
          </label>

          <div>
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5">
              <Image size={10} className="text-blue-400" />Фото к /start (опционально)
            </span>
            <div className="flex gap-2">
              <input value={welcomePhoto} onChange={e => setWelcomePhoto(e.target.value)}
                className="flex-1 bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="https://... или загрузите файл" />
              <label className={`px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-zinc-400 hover:text-white transition-all cursor-pointer flex items-center justify-center ${uploadingPhoto ? 'opacity-50 pointer-events-none' : ''}`}>
                {uploadingPhoto ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                <input type="file" accept="image/*" className="hidden" onChange={handlePhotoFile} disabled={uploadingPhoto} />
              </label>
            </div>
            {welcomePhoto && (
              <div className="mt-3 relative inline-block">
                <img src={welcomePhoto} alt="preview" className="h-28 rounded-xl object-cover border border-zinc-800"
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} />
                <button type="button" onClick={() => setWelcomePhoto('')}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-white text-xs flex items-center justify-center hover:bg-red-400 transition-colors">✕</button>
              </div>
            )}
          </div>

          <div>
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-2 flex items-center gap-1.5">
              <Link size={10} className="text-indigo-400" />Инлайн-кнопки под приветствием
            </span>
            <p className="text-[10px] text-zinc-600 mb-3 leading-relaxed">
              Тип <b className="text-zinc-400">Ссылка</b> — открывает URL. Тип <b className="text-zinc-400">Сообщение</b> — отправляет текст боту.
            </p>
            {inlineButtons.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет инлайн-кнопок</p>}
            <div className="space-y-3">
              {inlineButtons.map((btn, i) => (
                <div key={btn.id} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input value={btn.text} onChange={e => updateInlineButton(i, 'text', e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                      placeholder="Текст кнопки" />
                    <select value={btn.type} onChange={e => updateInlineButton(i, 'type', e.target.value as 'url' | 'message')}
                      className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-xs text-white focus:outline-none">
                      <option value="url">🔗 Ссылка</option>
                      <option value="message">💬 Сообщение</option>
                    </select>
                    <button type="button" onClick={() => removeInlineButton(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <input value={btn.value} onChange={e => updateInlineButton(i, 'value', e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder={btn.type === 'url' ? 'https://example.com' : 'Текст который будет отправлен боту...'} />
                </div>
              ))}
            </div>
            <button type="button" onClick={addInlineButton}
              className="w-full mt-3 py-2.5 rounded-xl border border-dashed border-indigo-500/30 text-indigo-400 text-[11px] font-bold uppercase tracking-wider hover:bg-indigo-500/5 transition-all flex items-center justify-center gap-1.5">
              <Plus size={12} /> Добавить инлайн-кнопку
            </button>
          </div>
        </Section>

        <Section title="Режим пересылки" icon={<Send size={13} className="text-blue-400" />}>
          <Toggle value={!!stg.forwardAll} onChange={v => updateStg('forwardAll', v)}
            label="Пересылать все сообщения в чат"
            sub="Без создания тикета — всё идёт в админ-чат (кнопки по-прежнему работают)" color="blue" />
          {stg.forwardAll && (
            <Toggle value={!!stg.forwardMessages} onChange={v => updateStg('forwardMessages', v)}
              label="Нативный форвард (без заголовка)"
              sub="Если включено — forward_message. Если выкл — copy_message с заголовком" color="zinc" />
          )}
        </Section>

        <Section title="Форум (Темы)" icon={<ShieldAlert size={13} className="text-emerald-400" />}>
          <div className="space-y-2">
            {[
              { k: 'useTopics',       label: 'Использовать Темы (Forum)', sub: 'Для супергрупп с включёнными темами', color: 'emerald' },
              { k: 'topicPerRequest', label: 'Новая ветка на каждый тикет', sub: 'Ticket System Mode', color: 'blue' },
              { k: 'anonymousTopics', label: 'Анонимные ID (Anon ID)', sub: 'Хешировать данные пользователей', color: 'zinc' },
            ].map(f => (
              <Toggle key={f.k} value={!!(stg as any)[f.k]} onChange={v => updateStg(f.k, v)}
                label={f.label} sub={f.sub} color={f.color} />
            ))}
          </div>
        </Section>

        <Section title="Заголовки сообщений" icon={<Hash size={13} className="text-zinc-400" />}>
          <div className="space-y-3">
            {[
              { k: 'firstMessageHeader',  ph: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>', label: 'Первое сообщение' },
              { k: 'ticketMessageHeader', ph: '🆘 <b>ЗАЯВКА [{btn}]:</b>',    label: 'Тикет / заявка' },
              { k: 'commonMessageHeader', ph: '📩 <b>СООБЩЕНИЕ:</b>',          label: 'Обычное сообщение' },
            ].map(f => (
              <label key={f.k} className="block">
                <span className="text-[9px] text-zinc-500 uppercase tracking-widest block mb-1">{f.label}</span>
                <input value={(stg as any)[f.k] || ''} onChange={e => updateStg(f.k, e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-600 transition-colors"
                  placeholder={f.ph} />
              </label>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2 pt-1">
            {[{ k: 'showHeaderName', l: 'Имя' }, { k: 'showHeaderUsername', l: 'Юзер' }, { k: 'showHeaderId', l: 'ID' }].map(f => (
              <button key={f.k} type="button" onClick={() => updateStg(f.k, !(stg as any)[f.k])}
                className={`flex items-center justify-between p-3 rounded-xl border text-[9px] font-bold uppercase transition-all ${(stg as any)[f.k] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                {f.l} {(stg as any)[f.k] ? <CheckSquare className="w-3 h-3" /> : <SquareIcon className="w-3 h-3" />}
              </button>
            ))}
          </div>
        </Section>

        <Section title="Безопасность и Анти-Флуд" icon={<Lock size={13} className="text-rose-400" />}>
          {[
            { key: 'rateLimit', label: 'Интервал анти-спама', sub: 'Сек. между сообщениями', step: '0.5', min: '0' },
            { key: 'autoBanThreshold', label: 'Лимит предупреждений', sub: 'Варнов до авто-бана', step: '1', min: '0' },
          ].map(f => (
            <div key={f.key} className="flex items-center justify-between p-4 rounded-xl bg-black border border-zinc-800">
              <div>
                <p className="text-xs font-bold text-white">{f.label}</p>
                <p className="text-[9px] text-zinc-500 uppercase">{f.sub}</p>
              </div>
              <input type="number" step={f.step} min={f.min}
                className="w-16 bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-center text-xs text-white focus:outline-none"
                value={(stg as any)[f.key]}
                onChange={e => {
                  const v = e.target.value;
                  updateStg(f.key, v === '' ? 0 : (f.step === '0.5' ? parseFloat(v) : parseInt(v)) || 0);
                }} />
            </div>
          ))}
        </Section>

        <Section title={`Кнопки (${buttons.length})`} icon={<Zap size={13} className="text-blue-400" />}>
          {buttons.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет кнопок</p>}
          <div className="space-y-3">
            {buttons.map((btn, i) => (
              <div key={btn.id || `btn-${i}`} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={btn.text || ''} onChange={e => updateButton(i, 'text', e.target.value)}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder="Текст кнопки" />
                  <select value={btn.type || 'default'} onChange={e => updateButton(i, 'type', e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-xs text-white focus:outline-none">
                    <option value="default">Обычная</option>
                    <option value="ticket">Тикетная</option>
                  </select>
                  <button type="button" onClick={() => removeButton(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea value={btn.response || ''} onChange={e => updateButton(i, 'response', e.target.value)} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ на кнопку..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={addButton}
            className="w-full py-2.5 rounded-xl border border-dashed border-blue-500/30 text-blue-400 text-[11px] font-bold uppercase tracking-wider hover:bg-blue-500/5 transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить кнопку
          </button>
        </Section>

        <Section title={`Триггеры (${triggers.length})`} icon={<MessageSquare size={13} className="text-purple-400" />}>
          {triggers.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет триггеров</p>}
          <div className="space-y-3">
            {triggers.map((trg, i) => (
              <div key={trg.id || `trg-${i}`} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={trg.keyword || ''} onChange={e => updateTrigger(i, 'keyword', e.target.value)}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder="Ключевое слово" />
                  <button type="button" onClick={() => removeTrigger(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea value={trg.response || ''} onChange={e => updateTrigger(i, 'response', e.target.value)} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ на триггер..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={addTrigger}
            className="w-full py-2.5 rounded-xl border border-dashed border-purple-500/30 text-purple-400 text-[11px] font-bold uppercase tracking-wider hover:bg-purple-500/5 transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить триггер
          </button>
        </Section>

        <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Crown size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-amber-300 uppercase tracking-widest mb-0.5">Разблокировать Pro</div>
              <div className="text-[11px] text-zinc-400">Неограниченные кнопки, триггеры, ИИ, рассылки, без рекламы</div>
            </div>
            <a href="/auth" className="px-3 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors shrink-0">Pro →</a>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
            <AlertTriangle size={14} className="flex-shrink-0" /> {error}
          </div>
        )}

        <div className="fixed bottom-0 left-0 right-0 p-4 bg-[#0a0a0a]/95 backdrop-blur-sm border-t border-zinc-800 flex justify-center">
          <button onClick={handleSave} disabled={saving}
            className={`px-8 py-3 rounded-2xl text-sm font-black uppercase tracking-widest transition-colors flex items-center gap-2 min-w-[200px] justify-center ${saveSuccess ? 'bg-emerald-600 text-white' : saving ? 'bg-zinc-800 text-zinc-600' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}>
            {saving ? <><Loader2 size={16} className="animate-spin" /> Сохранение...</>
              : saveSuccess ? <>✅ Сохранено!</>
              : <><Save size={16} /> Сохранить</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// ════════════════════════════════════════════════════════════════════════════════
// FREE VK BOT EDITOR
// ════════════════════════════════════════════════════════════════════════════════
const FreeVKBotEditor: React.FC<{
  bot: FreeBot;
  userId: string;
  onSave: (updated: FreeBot) => void;
  onBack: () => void;
}> = ({ bot, userId, onSave, onBack }) => {

  const initState = useCallback((b: FreeBot) => {
    const cfg         = b.config || {};
    const rawSettings = cfg.settings || {};
    const defaultSettings = {
      forwardAll: false, rateLimit: 1, autoBanThreshold: 3,
      anonymousTopics: false,
      showHeaderId: true, showHeaderName: true, showHeaderUsername: true,
      firstMessageHeader: '🆕 ПЕРВОЕ ОБРАЩЕНИЕ:',
      ticketMessageHeader: '🆘 ЗАЯВКА [{btn}]:',
      commonMessageHeader: '📩 СООБЩЕНИЕ:',
    };
    const peerRaw = cfg.vk_group_id || cfg.vkGroupId || cfg.adminChatId || '';
    return {
      name:         b.name,
      token:        b.token || cfg.token || '',
      welcome:      cfg.welcomeMessage || '',
      welcomePhoto: cfg.welcomePhoto   || '',
      adminId:      peerRaw ? String(peerRaw) : '',
      buttons:      (cfg.buttons  || []) as any[],
      triggers:     (cfg.triggers || []) as any[],
      inlineButtons:(cfg.inlineButtons || []) as InlineButton[],
      stg:          { ...defaultSettings, ...rawSettings },
    };
  }, []);

  const [name,          setName]          = useState(() => initState(bot).name);
  const [token,         setToken]         = useState(() => initState(bot).token);
  const [welcome,       setWelcome]       = useState(() => initState(bot).welcome);
  const [welcomePhoto,  setWelcomePhoto]  = useState(() => initState(bot).welcomePhoto);
  const [adminId,       setAdminId]       = useState(() => initState(bot).adminId);
  const [buttons,       setButtons]       = useState<any[]>(() => initState(bot).buttons);
  const [triggers,      setTriggers]      = useState<any[]>(() => initState(bot).triggers);
  const [inlineButtons, setInlineButtons] = useState<InlineButton[]>(() => initState(bot).inlineButtons);
  const [stg,           setStg]           = useState(() => initState(bot).stg);
  const [showToken,     setShowToken]     = useState(false);
  const [saving,        setSaving]        = useState(false);
  const [saveSuccess,   setSaveSuccess]   = useState(false);
  const [error,         setError]         = useState('');

  const prevBotIdRef = useRef(bot.id);
  useEffect(() => {
    if (prevBotIdRef.current !== bot.id) {
      prevBotIdRef.current = bot.id;
      const s = initState(bot);
      setName(s.name); setToken(s.token); setWelcome(s.welcome);
      setWelcomePhoto(s.welcomePhoto); setAdminId(s.adminId);
      setButtons(s.buttons); setTriggers(s.triggers);
      setInlineButtons(s.inlineButtons); setStg(s.stg);
      setError(''); setSaveSuccess(false);
    }
  }, [bot.id, initState]);

  const updateStg = useCallback((key: string, val: any) => setStg(prev => ({ ...prev, [key]: val })), []);

  const handleSave = async () => {
    if (saving) return;
    setSaving(true); setError(''); setSaveSuccess(false);
    try {
      const payload = {
        user_id: userId, name, token: token.trim() || undefined,
        buttons, triggers,
        config: {
          welcomeMessage: welcome, welcomePhoto,
          adminChatId: adminId, vk_group_id: adminId, vkGroupId: adminId,
          inlineButtons, settings: stg,
        },
      };
      const res = await fetch(FREE_API(`/vk/bots/${bot.id}/config`), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Ошибка сохранения (${res.status})`);
      }
      const updatedBot: FreeBot = {
        ...bot, name, platform: 'vk',
        token: token.trim() || bot.token,
        config: { ...(bot.config || {}), welcomeMessage: welcome, welcomePhoto, adminChatId: adminId, vk_group_id: adminId, inlineButtons, settings: stg, buttons, triggers },
      };
      onSave(updatedBot);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e: any) {
      setError(e.message || 'Неизвестная ошибка');
    } finally {
      setSaving(false);
    }
  };

  const addButton    = useCallback(() => setButtons(prev => [...prev, { id: `btn_${Date.now()}`, text: '', type: 'default', response: '' }]), []);
  const removeButton = useCallback((idx: number) => setButtons(prev => prev.filter((_, i) => i !== idx)), []);
  const updateButton = useCallback((idx: number, field: string, val: string) => setButtons(prev => prev.map((b, i) => i === idx ? { ...b, [field]: val } : b)), []);

  const addTrigger    = useCallback(() => setTriggers(prev => [...prev, { id: `trg_${Date.now()}`, keyword: '', response: '' }]), []);
  const removeTrigger = useCallback((idx: number) => setTriggers(prev => prev.filter((_, i) => i !== idx)), []);
  const updateTrigger = useCallback((idx: number, field: string, val: string) => setTriggers(prev => prev.map((t, i) => i === idx ? { ...t, [field]: val } : t)), []);

  const addInlineButton    = useCallback(() => setInlineButtons(prev => [...prev, { id: `inl_${Date.now()}`, text: '', type: 'url', value: '' }]), []);
  const removeInlineButton = useCallback((idx: number) => setInlineButtons(prev => prev.filter((_, i) => i !== idx)), []);
  const updateInlineButton = useCallback((idx: number, field: keyof InlineButton, val: string) => setInlineButtons(prev => prev.map((b, i) => i === idx ? { ...b, [field]: val } : b)), []);

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-2xl mx-auto p-6 md:p-10 space-y-5 pb-24">
        <div className="flex items-center gap-4 mb-2">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-black text-white">{bot.name}</h1>
            <span className="px-2 py-0.5 bg-[#4680C2]/20 rounded-full text-[10px] text-[#7ab3f0] font-bold uppercase tracking-widest mt-0.5 inline-block">Free · ВКонтакте</span>
          </div>
        </div>

        {/* VK info strip */}
        <div className="bg-[#4680C2]/5 border border-[#4680C2]/20 rounded-2xl p-4 flex items-center gap-3">
          <span className="text-lg">🔵</span>
          <p className="text-[11px] text-zinc-400 leading-relaxed">
            VK-бот работает через Community Token и Long Poll API. Темы (форум) не поддерживаются — только личные сообщения и беседы.
          </p>
        </div>

        {/* Гайд по VK токену */}
        <VKTokenGuide />

        <Section title="Основные настройки" icon={<Settings size={13} className="text-[#7ab3f0]" />}>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Название бота</span>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#4680C2] transition-colors"
              placeholder="Мой ВК-бот" />
          </label>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">VK Community Token</span>
            <div className="relative">
              <input type={showToken ? 'text' : 'password'} value={token} onChange={e => setToken(e.target.value)}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 pr-10 text-sm text-white font-mono focus:outline-none focus:border-[#4680C2] transition-colors"
                placeholder="vk1.a.Abc123..." />
              <button type="button" onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors">
                {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </label>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5">
              <Users size={10} className="text-amber-400" />peer_id беседы-администратора
              <span className="text-zinc-600">(опционально — автопривязка при добавлении в беседу)</span>
            </span>
            <input value={adminId} onChange={e => setAdminId(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500 transition-colors"
              placeholder="2000000001" />
          </label>
        </Section>

        <Section title="Приветствие" icon={<MessageSquare size={13} className="text-emerald-400" />}>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Текст приветствия</span>
            <textarea value={welcome} onChange={e => setWelcome(e.target.value)} rows={3}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors resize-none"
              placeholder="Добро пожаловать!" />
          </label>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5">
              <Image size={10} className="text-blue-400" />Фото к приветствию (URL)
            </span>
            <input value={welcomePhoto} onChange={e => setWelcomePhoto(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="https://..." />
          </label>

          {/* VK Inline — только URL */}
          <div>
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-2 flex items-center gap-1.5">
              <Link size={10} className="text-indigo-400" />Инлайн-кнопки (ссылки под сообщением)
            </span>
            <div className="bg-amber-500/5 border border-amber-500/15 rounded-xl p-2.5 mb-3">
              <p className="text-[10px] text-amber-400/80 leading-relaxed">
                ⚠️ ВКонтакте поддерживает только URL-кнопки. Кнопки типа «Сообщение» будут показаны как обычные reply-кнопки внизу.
              </p>
            </div>
            {inlineButtons.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет инлайн-кнопок</p>}
            <div className="space-y-3">
              {inlineButtons.map((btn, i) => (
                <div key={btn.id} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input value={btn.text} onChange={e => updateInlineButton(i, 'text', e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                      placeholder="Текст кнопки" />
                    <select value={btn.type} onChange={e => updateInlineButton(i, 'type', e.target.value as 'url' | 'message')}
                      className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-xs text-white focus:outline-none">
                      <option value="url">🔗 Ссылка</option>
                      <option value="message">💬 Сообщение</option>
                    </select>
                    <button type="button" onClick={() => removeInlineButton(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <input value={btn.value} onChange={e => updateInlineButton(i, 'value', e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder={btn.type === 'url' ? 'https://example.com' : 'Текст сообщения...'} />
                </div>
              ))}
            </div>
            <button type="button" onClick={addInlineButton}
              className="w-full mt-3 py-2.5 rounded-xl border border-dashed border-indigo-500/30 text-indigo-400 text-[11px] font-bold uppercase tracking-wider hover:bg-indigo-500/5 transition-all flex items-center justify-center gap-1.5">
              <Plus size={12} /> Добавить кнопку
            </button>
          </div>
        </Section>

        <Section title="Режим пересылки" icon={<Send size={13} className="text-blue-400" />}>
          <Toggle value={!!stg.forwardAll} onChange={v => updateStg('forwardAll', v)}
            label="Пересылать все сообщения в беседу"
            sub="Все входящие сообщения идут в беседу-администратора" color="blue" />
        </Section>

        <Section title="Безопасность" icon={<Lock size={13} className="text-rose-400" />}>
          {[
            { key: 'rateLimit', label: 'Интервал анти-спама', sub: 'Сек. между сообщениями', step: '0.5', min: '0' },
            { key: 'autoBanThreshold', label: 'Лимит предупреждений', sub: 'Варнов до авто-бана', step: '1', min: '0' },
          ].map(f => (
            <div key={f.key} className="flex items-center justify-between p-4 rounded-xl bg-black border border-zinc-800">
              <div>
                <p className="text-xs font-bold text-white">{f.label}</p>
                <p className="text-[9px] text-zinc-500 uppercase">{f.sub}</p>
              </div>
              <input type="number" step={f.step} min={f.min}
                className="w-16 bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-center text-xs text-white focus:outline-none"
                value={(stg as any)[f.key]}
                onChange={e => {
                  const v = e.target.value;
                  updateStg(f.key, v === '' ? 0 : (f.step === '0.5' ? parseFloat(v) : parseInt(v)) || 0);
                }} />
            </div>
          ))}
        </Section>

        <Section title={`Кнопки (${buttons.length})`} icon={<Zap size={13} className="text-blue-400" />}>
          {buttons.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет кнопок</p>}
          <div className="space-y-3">
            {buttons.map((btn, i) => (
              <div key={btn.id || `btn-${i}`} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={btn.text || ''} onChange={e => updateButton(i, 'text', e.target.value)}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder="Текст кнопки" />
                  <select value={btn.type || 'default'} onChange={e => updateButton(i, 'type', e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-xs text-white focus:outline-none">
                    <option value="default">Обычная</option>
                    <option value="ticket">Тикетная</option>
                  </select>
                  <button type="button" onClick={() => removeButton(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea value={btn.response || ''} onChange={e => updateButton(i, 'response', e.target.value)} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ на кнопку..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={addButton}
            className="w-full py-2.5 rounded-xl border border-dashed border-blue-500/30 text-blue-400 text-[11px] font-bold uppercase tracking-wider hover:bg-blue-500/5 transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить кнопку
          </button>
        </Section>

        <Section title={`Триггеры (${triggers.length})`} icon={<MessageSquare size={13} className="text-purple-400" />}>
          {triggers.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет триггеров</p>}
          <div className="space-y-3">
            {triggers.map((trg, i) => (
              <div key={trg.id || `trg-${i}`} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={trg.keyword || ''} onChange={e => updateTrigger(i, 'keyword', e.target.value)}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none"
                    placeholder="Ключевое слово" />
                  <button type="button" onClick={() => removeTrigger(i)} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea value={trg.response || ''} onChange={e => updateTrigger(i, 'response', e.target.value)} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ на триггер..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={addTrigger}
            className="w-full py-2.5 rounded-xl border border-dashed border-purple-500/30 text-purple-400 text-[11px] font-bold uppercase tracking-wider hover:bg-purple-500/5 transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить триггер
          </button>
        </Section>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
            <AlertTriangle size={14} className="flex-shrink-0" /> {error}
          </div>
        )}

        <div className="fixed bottom-0 left-0 right-0 p-4 bg-[#0a0a0a]/95 backdrop-blur-sm border-t border-zinc-800 flex justify-center">
          <button onClick={handleSave} disabled={saving}
            className={`px-8 py-3 rounded-2xl text-sm font-black uppercase tracking-widest transition-colors flex items-center gap-2 min-w-[200px] justify-center ${saveSuccess ? 'bg-emerald-600 text-white' : saving ? 'bg-zinc-800 text-zinc-600' : 'bg-[#4680C2] hover:bg-[#5a90d0] text-white'}`}>
            {saving ? <><Loader2 size={16} className="animate-spin" /> Сохранение...</>
              : saveSuccess ? <>✅ Сохранено!</>
              : <><Save size={16} /> Сохранить</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Analytics Panel ──────────────────────────────────────────────────────────
const FreeBotAnalytics: React.FC<{ bot: FreeBot; userId: string; onBack: () => void }> = ({ bot, userId, onBack }) => {
  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState<'stats' | 'audience'>('stats');

  const isVK = bot.platform === 'vk' || bot.id?.startsWith('fvk_');
  const apiPath = isVK
    ? FREE_API(`/vk/bots/${bot.id}/stats?user_id=${userId}`)
    : FREE_API(`/bots/${bot.id}/stats?user_id=${userId}`);

  const load = useCallback(() => {
    setLoading(true);
    fetch(apiPath)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [apiPath]);

  useEffect(() => { load(); }, [load]);

  const s    = data?.stats || {};
  const users: any[] = data?.connected_users || [];

  const statCards = [
    { label: 'Пользователей всего',    value: data?.users_count   ?? 0, color: 'text-cyan-400'   },
    { label: 'Активных',               value: data?.active_count  ?? 0, color: 'text-green-400'  },
    { label: 'Всего сообщений',        value: s.totalMessages     ?? 0, color: 'text-blue-400'   },
    { label: 'Входящих сегодня',       value: s.incomingToday     ?? 0, color: 'text-emerald-400' },
    { label: 'Исходящих сегодня',      value: s.outgoingToday     ?? 0, color: 'text-amber-400'  },
    { label: 'Активных 24ч',           value: s.activeUsers24h    ?? 0, color: 'text-purple-400' },
    { label: 'Заблокировано',          value: s.bannedCount       ?? 0, color: 'text-red-400'    },
    ...(!isVK ? [
      { label: 'Рассылок сегодня', value: s.broadcastsToday ?? 0, color: 'text-orange-400' },
      { label: 'Рассылок всего',   value: s.broadcastsTotal ?? 0, color: 'text-pink-400'   },
    ] : []),
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-6 md:p-10">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-black text-white">Аналитика</h1>
            <div className="text-xs text-zinc-500 truncate flex items-center gap-1.5">
              {isVK ? <span className="text-[#7ab3f0]">🔵 VK</span> : <span className="text-blue-400">✈️ TG</span>}
              {bot.name}
            </div>
          </div>
          <button onClick={load} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors text-zinc-400">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="flex gap-1 bg-zinc-900/60 border border-zinc-800 rounded-xl p-1 mb-5">
          {(['stats', 'audience'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${tab === t ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {t === 'stats' ? '📊 Статистика' : '👥 Аудитория'}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-zinc-600" /></div>
        ) : tab === 'stats' ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {statCards.map(c => (
                <div key={c.label} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                  <div className={`text-2xl font-black mb-1 ${c.color}`}>{c.value}</div>
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest leading-tight">{c.label}</div>
                </div>
              ))}
            </div>
            {s.history?.length > 0 && (
              <div className="mt-5 bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5">
                <h3 className="text-xs font-black text-zinc-400 uppercase tracking-widest mb-4">История (до 14 дней)</h3>
                <div className="flex items-end gap-1 h-24">
                  {s.history.map((d: any, i: number) => {
                    const maxVal = Math.max(...s.history.map((h: any) => (h.incoming || 0) + (h.outgoing || 0)), 1);
                    const barH   = Math.max(4, Math.round(((d.incoming + d.outgoing) / maxVal) * 88));
                    return (
                      <div key={d.date || i} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <div title={`${d.date}: вх ${d.incoming || 0}, исх ${d.outgoing || 0}`}
                          className={`w-full hover:opacity-80 transition-colors rounded-sm cursor-pointer ${isVK ? 'bg-[#4680C2]/40' : 'bg-blue-500/30'}`}
                          style={{ height: `${barH}px` }} />
                        <span className="text-[7px] text-zinc-700 group-hover:text-zinc-400">{d.date}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-2">
            {users.length === 0 ? (
              <div className="text-center py-12 text-zinc-600 text-sm">Нет пользователей</div>
            ) : (
              users.map((u: any) => {
                const name     = u.first_name || u.name || `ID ${u.id}`;
                const username = u.username ? `@${u.username}` : null;
                const isBanned = u.is_banned;
                const inTicket = u._in_ticket;
                const warns    = u.warns || 0;
                const lastSeen = u.last_seen
                  ? new Date(u.last_seen * 1000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
                  : '—';
                return (
                  <div key={u.id} className={`bg-zinc-900/60 border rounded-xl p-3 flex items-center gap-3 ${isBanned ? 'border-red-900/40' : 'border-zinc-800'}`}>
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-black ${isBanned ? 'bg-red-900/40 text-red-400' : 'bg-zinc-800 text-zinc-400'}`}>
                      {name[0]?.toUpperCase() || '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-sm font-bold text-white truncate">{name}</span>
                        {username && <span className="text-[10px] text-zinc-500">{username}</span>}
                        {isBanned  && <span className="text-[9px] bg-red-500/15 text-red-400 px-1.5 py-0.5 rounded-full font-bold uppercase">Бан</span>}
                        {inTicket  && <span className="text-[9px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded-full font-bold uppercase">В тикете</span>}
                        {warns > 0 && <span className="text-[9px] bg-amber-500/15 text-amber-400 px-1.5 py-0.5 rounded-full font-bold uppercase">{warns} предупр.</span>}
                      </div>
                      <div className="text-[10px] text-zinc-600 mt-0.5">ID: {u.id} · был {lastSeen}</div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ════════════════════════════════════════════════════════════════════════════════
// MAIN FREE PLAN PAGE
// ════════════════════════════════════════════════════════════════════════════════
type View = 'list' | 'editor' | 'vk-editor' | 'analytics';
type Platform = 'telegram' | 'vk';

const FreePlan: React.FC = () => {
  const navigate = useNavigate();

  const getUserId = (): string => {
    const direct = localStorage.getItem('user_id');
    if (direct && direct !== 'undefined' && direct !== 'null') return direct;
    try {
      const session = localStorage.getItem('active_session_user');
      if (session && session !== 'undefined' && session !== 'null') {
        const parsed = JSON.parse(session);
        if (parsed && parsed.id) return String(parsed.id);
      }
    } catch {}
    return '';
  };

  const userId = getUserId();

  const [view,        setView]        = useState<View>('list');
  const [platform,    setPlatform]    = useState<Platform>('telegram');
  const [activeBot,   setActiveBot]   = useState<FreeBot | null>(null);
  const [tgBots,      setTgBots]      = useState<FreeBot[]>([]);
  const [vkBots,      setVkBots]      = useState<FreeBot[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [creating,    setCreating]    = useState(false);
  const [newName,     setNewName]     = useState('');
  const [newToken,    setNewToken]    = useState('');
  const [showCreate,  setShowCreate]  = useState(false);
  const [statusMap,   setStatusMap]   = useState<Record<string, string>>({});
  const [loadError,   setLoadError]   = useState('');

  const bots = platform === 'telegram' ? tgBots : vkBots;

  const loadBots = useCallback(async () => {
    if (!userId) return;
    setLoading(true); setLoadError('');
    try {
      const [tgRes, vkRes] = await Promise.all([
        fetch(FREE_API(`/bots/${userId}`)),
        fetch(FREE_API(`/vk/bots/${userId}`)),
      ]);

      const tgList: FreeBot[] = tgRes.ok ? ((await tgRes.json()) || []).map((b: FreeBot) => ({ ...b, platform: 'telegram' as Platform })) : [];
      const vkList: FreeBot[] = vkRes.ok ? ((await vkRes.json()) || []).map((b: FreeBot) => ({ ...b, platform: 'vk' as Platform })) : [];

      setTgBots(Array.isArray(tgList) ? tgList : []);
      setVkBots(Array.isArray(vkList) ? vkList : []);

      setStatusMap(prev => {
        const next = { ...prev };
        [...tgList, ...vkList].forEach((b: FreeBot) => {
          if (!next[b.id] || next[b.id] === b.status) next[b.id] = b.status;
        });
        const allIds = new Set([...tgList, ...vkList].map((b: FreeBot) => b.id));
        Object.keys(next).forEach(id => { if (!allIds.has(id)) delete next[id]; });
        return next;
      });
    } catch (e: any) {
      setLoadError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) { setLoading(false); return; }
    loadBots();
  }, [userId, loadBots]);

  // Poll statuses
  useEffect(() => {
    const allBots = [...tgBots, ...vkBots];
    if (!allBots.length) return;
    const t = setInterval(() => {
      allBots.forEach(b => {
        fetch(`/api/bots/status/${b.id}`)
          .then(r => r.ok ? r.json() : null)
          .then(d => {
            if (d?.status) setStatusMap(prev => prev[b.id] === 'LOADING' ? prev : { ...prev, [b.id]: d.status });
          }).catch(() => {});
      });
    }, 5000);
    return () => clearInterval(t);
  }, [tgBots, vkBots]);

  const createBot = async () => {
    if (!newName.trim() || !newToken.trim()) return;
    setCreating(true);
    try {
      const isVK   = platform === 'vk';
      const apiUrl = isVK ? FREE_API('/vk/bots/create') : FREE_API('/bots/create');
      const r = await fetch(apiUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, name: newName.trim(), token: newToken.trim() }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || 'Ошибка создания');
      }
      const bot = { ...await r.json(), platform };
      if (isVK) {
        setVkBots(prev => [...prev, bot]);
      } else {
        setTgBots(prev => [...prev, bot]);
      }
      setStatusMap(prev => ({ ...prev, [bot.id]: bot.status || 'IDLE' }));
      setNewName(''); setNewToken(''); setShowCreate(false);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setCreating(false);
    }
  };

  const toggleBot = async (bot: FreeBot) => {
    const status    = statusMap[bot.id] || bot.status;
    if (status === 'LOADING') return;
    const isRunning = status === 'RUNNING';
    setStatusMap(prev => ({ ...prev, [bot.id]: 'LOADING' }));
    try {
      if (isRunning) {
        const r = await fetch(BOTS_API(`/bots/stop/${bot.id}`), { method: 'POST' });
        if (!r.ok) throw new Error(`Ошибка остановки (${r.status})`);
        setStatusMap(prev => ({ ...prev, [bot.id]: 'IDLE' }));
      } else {
        const r = await fetch(BOTS_API('/bots/start'), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: bot.id }),
        });
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || 'Ошибка запуска');
        }
        setStatusMap(prev => ({ ...prev, [bot.id]: 'RUNNING' }));
      }
    } catch (e: any) {
      alert(e.message);
      setStatusMap(prev => ({ ...prev, [bot.id]: status }));
    }
  };

  const deleteBot = async (bot: FreeBot) => {
    if (!window.confirm(`Удалить бот «${bot.name}»?`)) return;
    const isVK   = bot.platform === 'vk' || bot.id?.startsWith('fvk_');
    const apiUrl = isVK
      ? FREE_API(`/vk/bots/${userId}/${bot.id}`)
      : BOTS_API(`/bots/delete/${userId}/${bot.id}`);
    try {
      const r = await fetch(apiUrl, { method: 'DELETE' });
      if (!r.ok) throw new Error(`Ошибка удаления (${r.status})`);
      if (isVK) setVkBots(prev => prev.filter(b => b.id !== bot.id));
      else       setTgBots(prev => prev.filter(b => b.id !== bot.id));
      setStatusMap(prev => { const s = { ...prev }; delete s[bot.id]; return s; });
    } catch (e: any) {
      alert(e.message || 'Ошибка удаления');
    }
  };

  // ── Не авторизован ──────────────────────────────────────────────────────────
  if (!userId) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] text-white flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto font-black text-2xl">BE</div>
          <div>
            <h1 className="text-2xl font-black text-white">BotEngine Free</h1>
            <p className="text-zinc-500 text-sm mt-2">Войдите в аккаунт чтобы управлять ботами</p>
          </div>
          <div className="flex flex-col gap-3">
            <a href="/auth" className="block w-full py-3 bg-blue-600 hover:bg-blue-700 rounded-2xl text-sm font-black uppercase tracking-widest transition-colors text-center">Войти / Зарегистрироваться</a>
            <a href="/"     className="block w-full py-3 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-2xl text-sm font-bold text-zinc-400 transition-colors text-center">На главную</a>
          </div>
          <p className="text-[10px] text-zinc-700 uppercase tracking-widest">Free Plan · Без ограничений · С рекламой</p>
        </div>
      </div>
    );
  }

  // ── Editor views ────────────────────────────────────────────────────────────
  if (view === 'editor' && activeBot) {
    return (
      <FreeBotEditor bot={activeBot} userId={userId}
        onSave={updated => { setTgBots(prev => prev.map(b => b.id === updated.id ? updated : b)); setActiveBot(updated); }}
        onBack={() => { setView('list'); setActiveBot(null); }} />
    );
  }
  if (view === 'vk-editor' && activeBot) {
    return (
      <FreeVKBotEditor bot={activeBot} userId={userId}
        onSave={updated => { setVkBots(prev => prev.map(b => b.id === updated.id ? updated : b)); setActiveBot(updated); }}
        onBack={() => { setView('list'); setActiveBot(null); }} />
    );
  }
  if (view === 'analytics' && activeBot) {
    return (
      <FreeBotAnalytics bot={activeBot} userId={userId}
        onBack={() => { setView('list'); setActiveBot(null); }} />
    );
  }

  // ── Main list ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {userId && <AccountBadge userId={userId} />}

      <div className="max-w-2xl mx-auto p-6 md:p-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-black text-white">Free Plan</h1>
            <p className="text-zinc-500 text-sm mt-1">Бесплатные боты</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadBots} disabled={loading}
              className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-white disabled:opacity-50">
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
            <button onClick={() => navigate('/')}
              className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-white">
              <ArrowLeft size={16} />
            </button>
          </div>
        </div>

        {/* Platform tabs */}
        <div className="flex gap-1 bg-zinc-900/60 border border-zinc-800 rounded-xl p-1 mb-6">
          <button onClick={() => { setPlatform('telegram'); setShowCreate(false); }}
            className={`flex-1 py-2.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-1.5 ${platform === 'telegram' ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
            ✈️ Telegram
            {tgBots.length > 0 && <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-black ${platform === 'telegram' ? 'bg-blue-500 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{tgBots.length}</span>}
          </button>
          <button onClick={() => { setPlatform('vk'); setShowCreate(false); }}
            className={`flex-1 py-2.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-1.5 ${platform === 'vk' ? 'bg-[#4680C2] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
            🔵 ВКонтакте
            {vkBots.length > 0 && <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-black ${platform === 'vk' ? 'bg-[#5a90d0] text-white' : 'bg-zinc-800 text-zinc-400'}`}>{vkBots.length}</span>}
          </button>
        </div>

        {/* Features grid */}
<div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-6">
  {(platform === 'telegram' ? [
    { icon: '✅', label: 'Аналитика' }, { icon: '✅', label: 'Тикеты' },
    { icon: '✅', label: 'Модерация' }, { icon: '✅', label: 'Рассылки' },
    { icon: '✅', label: 'Топики'    }, { icon: '✅', label: 'Кнопки'  },
    { icon: '❌', label: 'ИИ-ассистент' }, { icon: '❌', label: 'Мини-приложения' },
  ] : [
    { icon: '✅', label: 'Аналитика' }, { icon: '✅', label: 'Тикеты' },
    { icon: '✅', label: 'Модерация' }, { icon: '✅', label: 'Рассылки' },
    { icon: '✅', label: 'Кнопки'   }, { icon: '✅', label: 'Триггеры'},
    { icon: '❌', label: 'ИИ-ассистент' }, { icon: '❌', label: 'Топики TG' },
  ]).map(f => (
    <div key={f.label} className="bg-zinc-900/40 border border-zinc-800 rounded-xl p-2.5 text-center">
      <div className="text-base mb-0.5">{f.icon}</div>
      <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">{f.label}</div>
    </div>
  ))}
</div>

        {/* Error */}
        {loadError && (
          <div className="flex items-center gap-2 p-3 mb-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
            <AlertTriangle size={14} className="flex-shrink-0" /> {loadError}
            <button onClick={loadBots} className="ml-auto text-red-400 hover:text-red-300 font-bold underline">Повторить</button>
          </div>
        )}

        {/* Bots list */}
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-zinc-600" /></div>
        ) : (
          <div className="space-y-3 mb-6">
            {bots.map(bot => {
              const status    = statusMap[bot.id] || bot.status;
              const isRunning = status === 'RUNNING';
              const isLoading = status === 'LOADING';
              const isVK      = bot.platform === 'vk' || bot.id?.startsWith('fvk_');
              return (
                <div key={bot.id} className={`bg-zinc-900/50 border rounded-2xl p-4 ${isVK ? 'border-[#4680C2]/20' : 'border-zinc-800'}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isRunning ? 'bg-green-400' : isLoading ? 'bg-amber-400 animate-pulse' : 'bg-zinc-600'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold text-white truncate">{bot.name}</div>
                      <div className="text-[10px] text-zinc-500 uppercase font-bold">
                        {isLoading ? 'Загрузка...' : isRunning ? 'Работает' : 'Остановлен'}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => toggleBot(bot)} disabled={isLoading}
                        className={`p-2 rounded-xl transition-all ${isLoading ? 'opacity-50 cursor-not-allowed' : isRunning ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400' : 'bg-green-500/10 hover:bg-green-500/20 text-green-400'}`}>
                        {isLoading ? <Loader2 size={14} className="animate-spin" /> : isRunning ? <Square size={14} /> : <Play size={14} />}
                      </button>
                      <button
                        onClick={() => {
                          setActiveBot(bot);
                          setView(isVK ? 'vk-editor' : 'editor');
                        }}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all">
                        <Settings size={14} />
                      </button>
                      <button onClick={() => { setActiveBot(bot); setView('analytics'); }}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all">
                        <BarChart2 size={14} />
                      </button>
                      <button onClick={() => deleteBot(bot)}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-all">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}

            {bots.length === 0 && !showCreate && (
              <div className="text-center py-10 text-zinc-600">
                <Bot size={32} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm font-bold">Нет ботов</p>
                <p className="text-xs mt-1">Создайте бесплатного {platform === 'vk' ? 'VK-' : 'Telegram-'}бота</p>
              </div>
            )}

            {!showCreate && (
              <button onClick={() => setShowCreate(true)}
                className={`w-full py-3 rounded-2xl border border-dashed text-sm font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${platform === 'vk' ? 'border-[#4680C2]/30 text-[#7ab3f0] hover:bg-[#4680C2]/5' : 'border-blue-500/30 text-blue-400 hover:bg-blue-500/5'}`}>
                <Plus size={16} /> Создать {platform === 'vk' ? 'VK-бота' : 'бота'}
              </button>
            )}

            {showCreate && (
              <div className="bg-zinc-900/60 border border-zinc-700 rounded-2xl p-4 space-y-3">
                <h3 className="text-xs font-black text-zinc-300 uppercase tracking-widest">
                  {platform === 'vk' ? '🔵 Новый VK-бот' : '✈️ Новый Telegram-бот'}
                </h3>

                {/* Гайд прямо в форме создания */}
                {platform === 'telegram' ? <TelegramTokenGuide /> : <VKTokenGuide />}

                <input value={newName} onChange={e => setNewName(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                  placeholder="Название бота" />
                <input value={newToken} onChange={e => setNewToken(e.target.value)} type="password"
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-blue-500"
                  placeholder={platform === 'vk' ? 'vk1.a.Abc123...' : 'Токен от @BotFather'} />
                <div className="flex gap-2">
                  <button onClick={createBot} disabled={creating || !newName.trim() || !newToken.trim()}
                    className={`flex-1 py-2.5 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-sm font-bold transition-colors flex items-center justify-center gap-2 ${platform === 'vk' ? 'bg-[#4680C2] hover:bg-[#5a90d0] text-white' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}>
                    {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Создать
                  </button>
                  <button onClick={() => { setShowCreate(false); setNewName(''); setNewToken(''); }}
                    className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-sm font-bold text-zinc-400 transition-colors">
                    Отмена
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pro upgrade */}
        <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Crown size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-amber-300 uppercase tracking-widest mb-0.5">Перейти на Pro</div>
              <div className="text-[11px] text-zinc-400">Без ограничений, без рекламы, ИИ, мини-приложения</div>
            </div>
            <a href="/auth" className="px-3 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors shrink-0">Pro →</a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FreePlan;

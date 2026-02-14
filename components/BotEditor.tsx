import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import {
  Settings, Cpu, BarChart3, Terminal, X, Save, Power,
  Ticket, Plus, MessageSquare, User, CheckSquare,
  Square, Zap, Layout, ShieldAlert, Lock, Trash2, AlertCircle, Globe,
  Send, Shuffle, Hash, Users, Link, Smartphone, ChevronDown
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  isAdminMode?: boolean;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, isAdminMode }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  // ── Типы платформ ──
  const isVK         = bot.platform === 'vk';
  const isPoster     = bot.platform === 'poster';
  const isRandomizer = bot.platform === 'randomizer';
  const isSupportBot = !isPoster && !isRandomizer;

  // Сбрасываем вкладку сразу при маунте и при смене бота/платформы
  useEffect(() => {
    const supportOnlyTabs = ['logic', 'interface', 'chat'];
    if ((isPoster || isRandomizer) && supportOnlyTabs.includes(activeTab)) {
      setActiveTab('settings');
    }
  }, [bot.id, bot.platform, isPoster, isRandomizer]);

  useEffect(() => {
    if (activeTab === 'chat') {
      api.getBotMessages(bot.id).then(setMessages).catch(() => setMessages([]));
    }
  }, [activeTab, bot.id]);

  const defaultSettings: BotConfig['settings'] = {
    useTopics: false, topicPerRequest: false, anonymousTopics: false,
    forwardToAdmin: true, antiSpam: true, showUserInfo: true, showUsername: true,
    autoApproveJoin: false, rateLimit: 1, autoBanThreshold: 3,
    showHeaderId: true, showHeaderName: true, showHeaderUsername: true,
    notifyOnStart: true, notifyOnBlock: true,
    firstMessageHeader: "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
    ticketMessageHeader: "🆘 <b>ЗАЯВКА [{btn}]:</b>",
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>"
  };
  const safeSettings = { ...defaultSettings, ...(bot.settings || {}) };

  // ── Helpers ──
  const handleLocalUpdate = (upd: BotConfig) => { setHasUnsavedChanges(true); onUpdate(upd); };
  const updateSetting = (key: keyof typeof defaultSettings, val: any) => {
    setHasUnsavedChanges(true);
    onUpdate({ ...bot, settings: { ...safeSettings, [key]: val } });
  };
  const syncState = async () => {
    setIsProcessing(true);
    try {
      const updated = await api.saveBot(bot.owner_id, bot);
      if (updated) onUpdate(updated);
      setHasUnsavedChanges(false);
      alert('Конфигурация сохранена!');
    } catch { alert('Ошибка при сохранении'); }
    finally { setIsProcessing(false); }
  };
  const handleToggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        const updated = await api.saveBot(bot.owner_id, bot);
        if (updated) onUpdate(updated);
        setHasUnsavedChanges(false);
        const res = await api.startBotOnServer(bot);
        if (res === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert(`Ошибка запуска: ${res}`);
      }
    } finally { setIsProcessing(false); }
  };

  // ── adminIds helper ──
  const adminIdsStr = (bot.adminIds || []).join(', ');
  const updateAdminIds = (str: string) => {
    const ids = str.split(',').map(s => s.trim()).filter(s => /^\d+$/.test(s)).map(Number);
    handleLocalUpdate({ ...bot, adminIds: ids });
  };

  // ── Вкладки по типу бота ──
  const tabs = [
    { id: 'settings', label: 'Основные',     icon: Settings,  always: true },
    { id: 'interface',label: 'Кнопки',       icon: Ticket,    always: false },
    { id: 'logic',    label: 'Триггеры',     icon: Zap,       always: false },
    { id: 'stats',    label: 'Аналитика',    icon: BarChart3, always: true  },
    { id: 'logs',     label: 'Терминал',     icon: Terminal,  always: true  },
    { id: 'chat',     label: 'CRM',          icon: MessageSquare, always: false },
  ].filter(t => t.always || isSupportBot);

  // ── Иконка заголовка ──
  const HeaderIcon = isPoster ? Send : isRandomizer ? Shuffle : (isVK ? Globe : Cpu);
  const platformColor = isPoster ? 'text-emerald-500' : isRandomizer ? 'text-purple-500' : isVK ? 'text-sky-500' : 'text-blue-500';
  const platformBadge = isPoster ? 'Постинг' : isRandomizer ? 'Рандомайзер' : isVK ? 'VK' : 'Telegram';
  const badgeStyle    = isPoster ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                        isRandomizer ? 'bg-purple-500/10 border-purple-500/20 text-purple-400' :
                        isVK ? 'bg-sky-500/10 border-sky-500/20 text-sky-400' :
                        'bg-blue-500/10 border-blue-500/20 text-blue-400';

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">

      {/* Баннер несохранённых изменений */}
      {hasUnsavedChanges && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-4 animate-bounce">
          <AlertCircle className="w-5 h-5" />
          <span className="text-xs font-black uppercase tracking-widest">Несохранённые изменения!</span>
          <button onClick={syncState} disabled={isProcessing} className="bg-white text-blue-600 px-4 py-1.5 rounded-xl font-black text-[10px] uppercase">
            Сохранить
          </button>
        </div>
      )}

      {/* Шапка */}
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? `border-current/30 bg-current/5 ${platformColor}` : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <HeaderIcon className="w-8 h-8" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-black text-white">{bot.name}</h1>
              <span className={`px-2 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest border ${badgeStyle}`}>{platformBadge}</span>
              {isAdminMode && <span className="px-2 py-1 bg-orange-500/10 border border-orange-500/20 rounded-lg text-orange-500 text-[8px] font-black uppercase tracking-widest">Support</span>}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-blue-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4">
          <button onClick={syncState} disabled={isProcessing} className={`px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${hasUnsavedChanges ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
            <Save className="w-4 h-4" /> Сохранить
          </button>
          <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase flex items-center gap-2 shadow-xl transition-all ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white'}`}>
            <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Стоп' : 'Запустить'}
          </button>
        </div>
      </header>

      {/* Вкладки */}
      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)}
            className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* ════════════════════════════════════════════
          ВКЛАДКА: НАСТРОЙКИ
      ════════════════════════════════════════════ */}
      {activeTab === 'settings' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

          {/* ══ ТИП БОТА — всегда col-span-2 ══ */}
          <div className="lg:col-span-2">
            <div className="bg-[#111] border border-zinc-800 p-6 rounded-[2.5rem]">
              <h2 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <ChevronDown className="w-3 h-3" /> Тип бота
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {([
                  { id: 'telegram',   label: 'TG Поддержка', sub: 'Чат с пользователями',  Icon: Smartphone, active: 'bg-blue-600/10 border-blue-500 text-blue-400'    },
                  { id: 'vk',         label: 'VK Поддержка', sub: 'Беседа ВКонтакте',       Icon: Globe,      active: 'bg-sky-600/10 border-sky-500 text-sky-400'        },
                  { id: 'poster',     label: 'TG Постинг',   sub: 'Публикация в канал',     Icon: Send,       active: 'bg-emerald-600/10 border-emerald-500 text-emerald-400' },
                  { id: 'randomizer', label: 'Рандомайзер',  sub: 'Розыгрыши и конкурсы',  Icon: Shuffle,    active: 'bg-purple-600/10 border-purple-500 text-purple-400' },
                ] as const).map(({ id, label, sub, Icon, active }) => (
                  <button key={id} type="button"
                    onClick={() => handleLocalUpdate({ ...bot, platform: id as any })}
                    className={`flex items-center gap-3 p-4 rounded-2xl border text-left transition-all ${
                      bot.platform === id ? active : 'bg-black border-zinc-800 text-zinc-500 hover:border-zinc-700'
                    }`}>
                    <Icon className="w-4 h-4 shrink-0" />
                    <div>
                      <div className="text-[10px] font-black uppercase">{label}</div>
                      <div className="text-[8px] opacity-60 font-medium">{sub}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Левая колонка */}
          <div className="space-y-8">
            <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                <Settings className="w-4 h-4 text-blue-500" /> Основные настройки
              </h2>
              <div className="space-y-5">

                {/* Платформа — показываем только для support-ботов */}
                {isSupportBot && (
                  <div className="flex bg-black p-1 rounded-2xl border border-zinc-800">
                    {['telegram', 'vk'].map(p => (
                      <button key={p} type="button"
                        onClick={() => handleLocalUpdate({ ...bot, platform: p as any })}
                        className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase transition-all ${bot.platform === p ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-zinc-500 hover:text-zinc-300'}`}>
                        {p === 'telegram' ? 'Telegram Bot' : 'VK Community'}
                      </button>
                    ))}
                  </div>
                )}

                {/* Токен */}
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                    {isVK ? 'ВКонтакте Access Token' : 'Telegram Bot Token'}
                  </span>
                  <input type="password"
                    placeholder={isVK ? 'Введите токен доступа группы' : 'Токен от @BotFather'}
                    className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono outline-none focus:border-blue-500 transition-all"
                    value={bot.token}
                    onChange={e => handleLocalUpdate({ ...bot, token: e.target.value })} />
                </label>

                {/* Группа/Форум — для support-ботов */}
                {isSupportBot && (
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                      {isVK ? 'ID беседы (peer_id)' : 'ID Группы Админов (Forum)'}
                    </span>
                    <input type="text"
                      placeholder={isVK ? '2000000010' : '-100...'}
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
                      value={isVK ? (bot.vkGroupId ?? bot.vk_group_id ?? '') : (bot.adminChatId ?? '')}
                      onChange={e => isVK
                        ? handleLocalUpdate({ ...bot, vkGroupId: e.target.value, vk_group_id: e.target.value })
                        : handleLocalUpdate({ ...bot, adminChatId: e.target.value })} />
                    {isVK && <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">peer_id беседы ВКонтакте: напр. 2000000010</p>}
                  </label>
                )}

                {/* Каналы — для постера (список) */}
                {isPoster && (
                  <div className="space-y-3">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Hash className="w-3 h-3 text-emerald-500" />Каналы для публикации
                    </span>
                    {(bot.channels || (bot.channelId ? [bot.channelId] : [])).map((ch: string, i: number) => (
                      <div key={i} className="flex gap-2">
                        <input type="text"
                          className="flex-1 bg-black border border-zinc-800 p-4 rounded-2xl text-white text-sm outline-none focus:border-emerald-500 transition-all"
                          value={ch}
                          placeholder="@mychannel или -1001234567890"
                          onChange={e => {
                            const chs = [...(bot.channels || [bot.channelId || ''])];
                            chs[i] = e.target.value;
                            handleLocalUpdate({ ...bot, channels: chs, channelId: chs[0] || '' });
                          }} />
                        <button type="button"
                          onClick={() => {
                            const chs = (bot.channels || [bot.channelId || '']).filter((_: string, idx: number) => idx !== i);
                            handleLocalUpdate({ ...bot, channels: chs, channelId: chs[0] || '' });
                          }}
                          className="px-3 py-2 rounded-xl bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition-all text-xs font-bold">
                          ✕
                        </button>
                      </div>
                    ))}
                    <button type="button"
                      onClick={() => {
                        const chs = [...(bot.channels || (bot.channelId ? [bot.channelId] : []))];
                        chs.push('');
                        handleLocalUpdate({ ...bot, channels: chs });
                      }}
                      className="w-full py-3 rounded-2xl border border-dashed border-emerald-500/30 text-emerald-500 text-[10px] font-black uppercase tracking-wider hover:bg-emerald-500/5 transition-all">
                      + Добавить канал
                    </button>
                    <p className="text-[8px] text-zinc-600 ml-2 uppercase font-bold">Бот должен быть администратором каждого канала</p>
                  </div>
                )}

                {/* Канал + ссылка — для рандомайзера */}
                {isRandomizer && (<>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Hash className="w-3 h-3 text-purple-500" />Канал розыгрышей
                    </span>
                    <input type="text"
                      placeholder="@lotchannel или -1001234567890"
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-purple-500 transition-all"
                      value={bot.lotChannel || ''}
                      onChange={e => handleLocalUpdate({ ...bot, lotChannel: e.target.value })} />
                    <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">Бот — администратор этого канала</p>
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Link className="w-3 h-3 text-purple-400" />Username бота
                    </span>
                    <input type="text"
                      placeholder="@MyLotteryBot"
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-purple-500 transition-all"
                      value={bot.botLink || ''}
                      onChange={e => handleLocalUpdate({ ...bot, botLink: e.target.value })} />
                    <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">Для генерации deep-link ссылок участия</p>
                  </label>
                </>)}

                {/* ID администраторов — для всех типов */}
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                    <Users className="w-3 h-3 text-amber-500" />ID администраторов бота
                  </span>
                  <input type="text"
                    placeholder="123456789, 987654321"
                    className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-amber-500 transition-all"
                    value={adminIdsStr}
                    onChange={e => updateAdminIds(e.target.value)} />
                  <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">
                    {isPoster || isRandomizer ? 'Только эти пользователи могут управлять ботом' : 'Могут делать /broadcast прямо в боте'}
                  </p>
                </label>

                {/* Приветствие — не для постера */}
                {!isPoster && (
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                      {isVK ? 'Текст приветствия' : 'Приветствие (/start)'}
                    </span>
                    <textarea
                      placeholder="Текст для команды /start"
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] outline-none text-xs focus:border-blue-500 transition-all resize-none"
                      value={bot.welcomeMessage || ''}
                      onChange={e => handleLocalUpdate({ ...bot, welcomeMessage: e.target.value })} />
                  </label>
                )}

                <p className="text-[8px] text-zinc-600 uppercase font-black tracking-widest opacity-50 ml-2">* Данные синхронизируются (согласно .env)</p>
              </div>
            </section>

            {/* Инфо-плашки для постера/рандомайзера */}
            {isPoster && (
              <div className="bg-emerald-500/5 border border-emerald-500/20 p-8 rounded-[2.5rem] space-y-3">
                <h3 className="text-sm font-black text-emerald-400 uppercase flex items-center gap-2">
                  <Send className="w-4 h-4" />Бот постинга — возможности
                </h3>
                <div className="text-[10px] text-zinc-400 leading-relaxed space-y-1.5">
                  <p>✅ <b>Контент:</b> текст, фото, видео, GIF, аудио, документ, стикер</p>
                  <p>✅ <b>Форматирование:</b> выделяй текст прямо в Telegram — жирный, курсив, код</p>
                  <p>✅ <b>Несколько каналов:</b> публикация в один или все сразу</p>
                  <p>✅ <b>Кнопки:</b> <code className="text-emerald-400">Текст | https://url</code> · столбцом или строчкой</p>
                  <p>✅ <b>Расписание:</b> через N минут / часов или точная дата</p>
                  <p>✅ <b>Очередь постов:</b> список запланированных + отмена</p>
                  <p className="text-zinc-600 mt-2">Управление: /start → wizard</p>
                </div>
              </div>
            )}

            {isRandomizer && (
              <div className="bg-purple-500/5 border border-purple-500/20 p-8 rounded-[2.5rem] space-y-3">
                <h3 className="text-sm font-black text-purple-400 uppercase flex items-center gap-2">
                  <Shuffle className="w-4 h-4" />Рандомайзер — возможности
                </h3>
                <div className="text-[10px] text-zinc-400 leading-relaxed space-y-1.5">
                  <p>✅ <b>Розыгрыши</b> с публикацией в канал + кнопкой «Участвовать»</p>
                  <p>✅ <b>Проверка подписки</b> на канал перед участием</p>
                  <p>✅ <b>Финиш</b>: по времени или по числу участников</p>
                  <p>✅ <b>Авто-выбор победителей</b> и уведомление</p>
                  <p>✅ <b>/broadcast</b> — рассылка по всем участникам</p>
                  <p className="text-zinc-600 mt-2">Управление: /start → 🛠 Панель → Создать розыгрыш</p>
                </div>
              </div>
            )}

            {/* Конструктор шапки — только для support-ботов */}
            {isSupportBot && (
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Layout className="w-4 h-4 text-emerald-500" />Конструктор шапки сообщений
                </h2>
                <div className="space-y-4">
                  {[
                    { key: 'firstMessageHeader',  label: 'Заголовок первого обращения', ph: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>' },
                    { key: 'ticketMessageHeader',  label: 'Заголовок заявки (кнопки)',  ph: '🆘 <b>ЗАЯВКА [{btn}]:</b>'  },
                    { key: 'commonMessageHeader',  label: 'Обычное сообщение',          ph: '📩 <b>СООБЩЕНИЕ:</b>'        },
                  ].map(f => (
                    <div key={f.key}>
                      <span className="text-[9px] font-bold text-zinc-500 uppercase ml-2">{f.label}</span>
                      <input
                        className="w-full mt-1.5 bg-black border border-zinc-800 p-4 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all"
                        value={safeSettings[f.key as keyof typeof safeSettings] as string || ''}
                        onChange={e => updateSetting(f.key as any, e.target.value)}
                        placeholder={f.ph} />
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-3 pt-2">
                  {[{k:'showHeaderName',l:'Имя'},{k:'showHeaderUsername',l:'Юзер'},{k:'showHeaderId',l:'ID'}].map(f => (
                    <button key={f.k} onClick={() => updateSetting(f.k as any, !safeSettings[f.k as keyof typeof safeSettings])}
                      className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings[f.k as keyof typeof safeSettings] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                      {f.l} {safeSettings[f.k as keyof typeof safeSettings] ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Правая колонка — только для support-ботов */}
          {isSupportBot && (
            <div className="space-y-8">
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Lock className="w-4 h-4 text-rose-500" />Безопасность и Анти-Флуд
                </h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                    <div><p className="text-xs font-bold text-white">Интервал анти-спама</p><p className="text-[9px] text-zinc-500 uppercase">Сек. между сообщениями</p></div>
                    <input type="number" step="0.5" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white"
                      value={safeSettings.rateLimit} onChange={e => updateSetting('rateLimit', parseFloat(e.target.value))} />
                  </div>
                  <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                    <div><p className="text-xs font-bold text-white">Лимит Предупреждений</p><p className="text-[9px] text-zinc-500 uppercase">Варнов до авто-бана</p></div>
                    <input type="number" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white"
                      value={safeSettings.autoBanThreshold} onChange={e => updateSetting('autoBanThreshold', parseInt(e.target.value))} />
                  </div>
                </div>
              </section>

              <div className={`bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6 transition-all ${isVK ? 'opacity-40 select-none' : ''}`}>
                <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <ShieldAlert className={`w-4 h-4 ${isVK ? 'text-zinc-500' : 'text-emerald-500'}`} />Форум (Темы)
                  {isVK && <span className="text-[9px] bg-rose-500/20 text-rose-500 px-2 py-0.5 rounded-md ml-auto">Только Telegram</span>}
                </h3>
                <div className="space-y-3">
                  {[
                    {k:'useTopics',       l:'Использовать Темы (Forum)', sub:'Для супергрупп',        c:'emerald'},
                    {k:'topicPerRequest', l:'Новая ветка на каждый тикет', sub:'Ticket System Mode', c:'blue'},
                    {k:'anonymousTopics', l:'Анонимные ID (Anon ID)', sub:'Хешировать данные',       c:'zinc'},
                  ].map(f => (
                    <button key={f.k} disabled={isVK}
                      onClick={() => updateSetting(f.k as any, !safeSettings[f.k as keyof typeof safeSettings])}
                      className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${
                        !isVK && safeSettings[f.k as keyof typeof safeSettings]
                          ? f.c === 'emerald' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                          : f.c === 'blue' ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                          : 'bg-zinc-800 text-white'
                          : 'bg-black border-zinc-800 text-zinc-600'
                      }`}>
                      <div className="text-left">
                        <p className="text-xs font-bold">{f.l}</p>
                        <p className="text-[9px] uppercase opacity-50">{f.sub}</p>
                      </div>
                      {isVK ? <Lock className="w-4 h-4" /> : (safeSettings[f.k as keyof typeof safeSettings] ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Зона опасных действий */}
          <div className="lg:col-span-2 mt-4">
            {isAdminMode ? (
              <div className="p-6 border border-zinc-800 bg-zinc-900/40 rounded-[2rem] flex items-center gap-4 opacity-50 pointer-events-none">
                <div className="p-3 bg-zinc-800 rounded-xl"><Lock size={20} className="text-zinc-500" /></div>
                <div>
                  <h4 className="text-[10px] font-black uppercase text-zinc-400 tracking-widest">Admin Protection</h4>
                  <p className="text-[9px] text-zinc-600 uppercase">Deletion disabled in Support Mode</p>
                </div>
              </div>
            ) : (
              <button onClick={() => window.confirm('Вы точно хотите удалить этот инстанс?') && onDelete()}
                className="w-full p-5 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-3xl border border-rose-500/10 hover:bg-rose-500/20 transition-all flex items-center justify-center gap-2">
                <Trash2 className="w-4 h-4" />Удалить навсегда
              </button>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: КНОПКИ (только для support-ботов)
      ════════════════════════════════════════════ */}
      {activeTab === 'interface' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-black text-white uppercase">Конструктор Кнопок</h2>
            <button onClick={() => handleLocalUpdate({ ...bot, buttons: [...(bot.buttons||[]), {text:'',response:'',type:'message'}] })}
              className="bg-blue-600 px-8 py-4 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-blue-600/20 hover:bg-blue-500 transition-all">
              <Plus className="w-4 h-4" />Новая кнопка
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {(bot.buttons||[]).map((btn, i) => (
              <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative border-t-4 border-t-blue-500/20 shadow-xl">
                <button onClick={() => handleLocalUpdate({...bot,buttons:bot.buttons.filter((_,idx)=>idx!==i)})}
                  className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500 transition-colors"><X className="w-5 h-5" /></button>
                <div className="space-y-5">
                  <label className="block">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Текст на кнопке</span>
                    <input className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-blue-500"
                      value={btn.text} onChange={e => { const nb=[...bot.buttons]; nb[i].text=e.target.value; handleLocalUpdate({...bot,buttons:nb}); }} />
                  </label>
                  <label className="block">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Ответ системы</span>
                    <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] outline-none focus:border-blue-500 resize-none"
                      value={btn.response} onChange={e => { const nb=[...bot.buttons]; nb[i].response=e.target.value; handleLocalUpdate({...bot,buttons:nb}); }} />
                  </label>
                  <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
                    {['message','request'].map(type => (
                      <button key={type} onClick={() => { const nb=[...bot.buttons]; nb[i].type=type as any; handleLocalUpdate({...bot,buttons:nb}); }}
                        className={`flex-1 py-2.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type===type?'bg-blue-600 text-white shadow-lg':'text-zinc-600 hover:text-zinc-400'}`}>
                        {type==='message'?'Обычный ответ':'🆘 Заявка (Тикет)'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: ТРИГГЕРЫ (только для support-ботов)
      ════════════════════════════════════════════ */}
      {activeTab === 'logic' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in duration-500">
          <div className="flex justify-between items-end mb-6">
            <h2 className="text-2xl font-black text-white uppercase">Триггеры авто-ответа</h2>
            <button onClick={() => handleLocalUpdate({...bot,triggers:[...(bot.triggers||[]),{keyword:'',response:''}]})}
              className="bg-emerald-600 px-8 py-4 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all">
              <Plus className="w-4 h-4" />Новый триггер
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {(bot.triggers||[]).map((trig,i) => (
              <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative border-t-4 border-t-emerald-500/20 shadow-xl">
                <button onClick={() => handleLocalUpdate({...bot,triggers:bot.triggers.filter((_,idx)=>idx!==i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500"><X className="w-5 h-5" /></button>
                <input placeholder="Ключевое слово" className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-emerald-500"
                  value={trig.keyword} onChange={e => { const nt=[...bot.triggers]; nt[i].keyword=e.target.value; handleLocalUpdate({...bot,triggers:nt}); }} />
                <textarea placeholder="Что бот должен ответить..." className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm outline-none min-h-[120px] focus:border-emerald-500"
                  value={trig.response} onChange={e => { const nt=[...bot.triggers]; nt[i].response=e.target.value; handleLocalUpdate({...bot,triggers:nt}); }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CRM */}
      {activeTab === 'chat' && isSupportBot && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] h-[700px] overflow-hidden flex flex-col p-8 shadow-2xl animate-in fade-in duration-500">
          <h2 className="text-sm font-black text-white uppercase mb-6 flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-blue-500" />CRM История сообщений
          </h2>
          <div className="flex-1 overflow-y-auto no-scrollbar space-y-6 pr-4">
            {messages.length === 0 ? (
              <p className="text-center text-zinc-700 py-32 uppercase text-[10px] font-black tracking-widest opacity-20">История пуста</p>
            ) : messages.map((m,i) => (
              <div key={i} className={`flex gap-4 items-start ${m.is_admin?'flex-row-reverse text-right':''} animate-in slide-in-from-bottom-2 duration-300`}>
                <div className={`p-5 rounded-3xl max-w-[75%] text-sm shadow-lg ${m.is_admin?'bg-blue-600 text-white rounded-tr-none':'bg-black/60 border border-zinc-800 text-zinc-300 rounded-tl-none'}`}>
                  <p className="text-[9px] font-black uppercase opacity-40 mb-2">{m.user?.name} | {new Date(m.timestamp).toLocaleTimeString()}</p>
                  <div className="leading-relaxed whitespace-pre-wrap">{m.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Аналитика и логи */}
      {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
      {activeTab === 'logs'  && <BotConsole botId={bot.id} />}

    </div>
  );
};

export default BotEditor;


import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { 
  Settings, Cpu, BarChart3, Terminal, X, Save, Power, 
  Ticket, Plus, MessageSquare, User, CheckSquare, 
  Square, Zap, Bell, Shield, Sliders, Layout, ShieldAlert, Lock, Trash2, ShieldCheck, AlertCircle, Type
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  const defaultSettings: BotConfig['settings'] = {
    useTopics: false,
    topicPerRequest: false,
    anonymousTopics: false,
    forwardToAdmin: true,
    antiSpam: true,
    showUserInfo: true,
    showUsername: true,
    autoApproveJoin: false,
    rateLimit: 1,
    autoBanThreshold: 3,
    showHeaderId: true,
    showHeaderName: true,
    showHeaderUsername: true,
    notifyOnStart: true,
    notifyOnBlock: true,
    firstMessageHeader: "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
    ticketMessageHeader: "🆘 <b>ЗАЯВКА:</b>",
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>"
  };

  const safeSettings = { ...defaultSettings, ...(bot.settings || {}) };

  useEffect(() => {
    if (activeTab === 'chat') {
        api.getBotMessages(bot.id).then(setMessages).catch(() => setMessages([]));
    }
  }, [activeTab, bot.id]);

  const handleToggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        await api.saveBot(bot.owner_id, bot);
        const res = await api.startBotOnServer(bot);
        if (res === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert(`Ошибка запуска: ${res}`);
      }
    } finally { setIsProcessing(false); }
  };

  const updateSetting = (key: keyof typeof defaultSettings, val: any) => {
    onUpdate({ ...bot, settings: { ...safeSettings, [key]: val } });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl relative overflow-hidden">
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? 'bg-blue-500/10 border-blue-500/30 text-blue-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4 relative z-10">
           <button onClick={() => api.saveBot(bot.owner_id, bot).then(() => alert("Конфигурация сохранена!"))} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all">
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase transition-all flex items-center gap-2 shadow-xl ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Основные', icon: Settings},
          {id: 'interface', label: 'Меню (Кнопки)', icon: Ticket},
          {id: 'logic', label: 'Триггеры', icon: Zap},
          {id: 'chat', label: 'CRM Чат', icon: MessageSquare},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Терминал', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}>
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-8">
              <section className="space-y-6">
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Type className="w-4 h-4 text-amber-500" /> Шаблоны заголовков
                </h2>
                <div className="space-y-4">
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Первое обращение</span>
                    <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white outline-none focus:border-blue-500" value={safeSettings.firstMessageHeader} onChange={e => updateSetting('firstMessageHeader', e.target.value)} />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Тикет / Заявка</span>
                    <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white outline-none focus:border-blue-500" value={safeSettings.ticketMessageHeader} onChange={e => updateSetting('ticketMessageHeader', e.target.value)} />
                    <p className="text-[9px] text-zinc-600 mt-1 ml-2 uppercase">Используйте {"{btn}"} для названия кнопки</p>
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Обычное сообщение</span>
                    <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white outline-none focus:border-blue-500" value={safeSettings.commonMessageHeader} onChange={e => updateSetting('commonMessageHeader', e.target.value)} />
                  </label>
                </div>
              </section>

              <section className="space-y-6">
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Layout className="w-4 h-4 text-emerald-500" /> Виджет данных юзера
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {[{k: 'showHeaderName', l: 'Имя'}, {k: 'showHeaderUsername', l: 'Юзер'}, {k: 'showHeaderId', l: 'ID'}].map(f => (
                    <button key={f.k} onClick={() => updateSetting(f.k as any, !safeSettings[f.k as keyof typeof safeSettings])} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings[f.k as keyof typeof safeSettings] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                      {f.l} {safeSettings[f.k as keyof typeof safeSettings] ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                    </button>
                  ))}
                </div>
              </section>
            </div>
            
            <div className="space-y-8">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                  <h3 className="text-sm font-black text-white uppercase flex items-center gap-2"><Lock className="w-4 h-4 text-rose-500" /> Безопасность и Анти-Флуд</h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                      <div><p className="text-xs font-bold text-white">Интервал спама (сек)</p><p className="text-[9px] text-zinc-500 uppercase">Между сообщениями</p></div>
                      <input type="number" step="0.5" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white" value={safeSettings.rateLimit} onChange={e => updateSetting('rateLimit', parseFloat(e.target.value))} />
                    </div>
                    <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                      <div><p className="text-xs font-bold text-white">Авто-бан (Лимит варнов)</p><p className="text-[9px] text-zinc-500 uppercase">До блокировки</p></div>
                      <input type="number" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white" value={safeSettings.autoBanThreshold} onChange={e => updateSetting('autoBanThreshold', parseInt(e.target.value))} />
                    </div>
                  </div>
                </div>

                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2"><ShieldAlert className="w-4 h-4 text-emerald-500" /> Форум (Темы)</h3>
                    <div className="space-y-3">
                      <button onClick={() => updateSetting('useTopics', !safeSettings.useTopics)} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.useTopics ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        <div className="text-left"><p className="text-xs font-bold">Использовать Темы (Forum)</p></div>
                        {safeSettings.useTopics ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>
                      <button onClick={() => updateSetting('topicPerRequest', !safeSettings.topicPerRequest)} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.topicPerRequest ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        <div className="text-left"><p className="text-xs font-bold">Тема на каждый тикет</p></div>
                        {safeSettings.topicPerRequest ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>
                    </div>
                </div>
                <button onClick={() => window.confirm("Вы точно хотите удалить?") && onDelete()} className="w-full p-5 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-3xl border border-rose-500/10 hover:bg-rose-500/10 transition-all flex items-center justify-center gap-2">
                    <Trash2 className="w-4 h-4" /> Удалить бота безвозвратно
                </button>
            </div>
          </div>
        )}
        
        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex justify-between items-center mb-6"><h2 className="text-2xl font-black text-white uppercase">Кнопки меню</h2><button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 px-8 py-4 rounded-2xl text-[11px] font-black text-white uppercase transition-all">+ Добавить кнопку</button></div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative border-t-4 border-t-blue-500/20 shadow-xl">
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500 transition-colors"><X className="w-5 h-5" /></button>
                    <label className="block"><span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Текст кнопки</span><input className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-blue-500" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} /></label>
                    <label className="block"><span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Ответ бота</span><textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] outline-none focus:border-blue-500 resize-none" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} /></label>
                    <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
                      {['message', 'request'].map(type => (
                        <button key={type} onClick={() => { const nb = [...bot.buttons]; nb[i].type = type as any; onUpdate({...bot, buttons: nb}); }} className={`flex-1 py-2.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type === type ? 'bg-blue-600 text-white' : 'text-zinc-600'}`}>{type === 'message' ? 'Обычный ответ' : '🆘 Тикет (Заявка)'}</button>
                      ))}
                    </div>
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-end mb-6"><h2 className="text-2xl font-black text-white uppercase">Авто-ответы</h2><button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-emerald-600 px-8 py-4 rounded-2xl text-[10px] font-black text-white uppercase">+ Новый триггер</button></div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative border-t-4 border-t-emerald-500/20 shadow-xl">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500"><X className="w-5 h-5" /></button>
                    <input placeholder="Ключевое слово" className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-emerald-500" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    <textarea placeholder="Ответ..." className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm outline-none min-h-[120px] focus:border-emerald-500 resize-none" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] h-[700px] overflow-hidden flex flex-col p-8 shadow-2xl">
            <h2 className="text-sm font-black text-white uppercase mb-6 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-blue-500" /> CRM Чат (Последние 50)</h2>
            <div className="flex-1 overflow-y-auto no-scrollbar space-y-6">
              {messages.length === 0 ? <p className="text-center text-zinc-700 py-32 font-black uppercase text-[10px] tracking-widest opacity-20">История пуста</p> : messages.map((m, i) => (
                <div key={i} className={`flex gap-4 items-start ${m.is_admin ? 'flex-row-reverse text-right' : ''}`}>
                   <div className={`p-5 rounded-3xl max-w-[75%] text-sm ${m.is_admin ? 'bg-blue-600 text-white' : 'bg-black/60 border border-zinc-800 text-zinc-300'}`}>
                      <p className="text-[9px] font-black uppercase opacity-40 mb-2">{m.user?.name} | {new Date(m.timestamp).toLocaleTimeString()}</p>
                      <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>
                   </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
        {activeTab === 'logs' && <BotConsole botId={bot.id} />}
      </div>
    </div>
  );
};

export default BotEditor;

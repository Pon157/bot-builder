import React, { useState } from 'react';
import { BotConfig } from '../types';
import { api } from '../services/apiService';
import { Send, CheckCircle2, AlertCircle, Bot as BotIcon, Radio, Shuffle } from 'lucide-react';

interface BroadcastManagerProps {
  bots: BotConfig[];
}

const BroadcastManager: React.FC<BroadcastManagerProps> = ({ bots }) => {
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{success: number, failed: number} | null>(null);

  const toggleBot = (id: string) => {
    setSelectedBotIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSend = async () => {
    if (!message || selectedBotIds.length === 0) return;
    setSending(true);
    setResult(null);
    try {
      const res = await api.sendBroadcast(selectedBotIds, message);
      if (res) {
        setResult(res);
        setMessage('');
        setSelectedBotIds([]);
      }
    } catch {
      alert('Ошибка при выполнении рассылки');
    } finally {
      setSending(false);
    }
  };

  // Постинг-боты нельзя включать в рассылку — у них нет базы пользователей
  const broadcastEligible = bots.filter(
    b => b.status === 'RUNNING' && b.platform !== 'poster'
  );

  // Иконка и цвет по платформе
  const platformMeta = (platform?: string) => {
    switch (platform) {
      case 'vk':         return { icon: '🌐', color: 'text-sky-400',    badge: 'VK' };
      case 'randomizer': return { icon: '🎲', color: 'text-purple-400', badge: 'Rand' };
      default:           return { icon: '🤖', color: 'text-blue-400',   badge: 'TG' };
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 md:space-y-8 animate-in fade-in duration-500 pb-10">
      <header>
        <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight uppercase">
          Глобальная рассылка
        </h1>
        <p className="text-zinc-500 text-sm font-medium mt-1">
          Трансляция сообщений по всей базе пользователей выбранных ботов.
        </p>
      </header>

      {result && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-6 rounded-3xl flex items-center justify-between animate-in slide-in-from-top-4">
          <div className="flex items-center gap-4">
            <CheckCircle2 className="text-emerald-500 w-8 h-8 shrink-0" />
            <div>
              <p className="text-white font-black text-sm uppercase">Рассылка завершена</p>
              <p className="text-emerald-500/70 text-xs font-bold uppercase">
                Успешно: {result.success} | Ошибок: {result.failed}
              </p>
            </div>
          </div>
          <button
            onClick={() => setResult(null)}
            className="text-zinc-500 hover:text-white text-[10px] font-black uppercase ml-4 shrink-0"
          >
            Закрыть
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
        {/* Левая колонка — текст сообщения */}
        <div className="md:col-span-2 bg-[#111] border border-zinc-800 p-6 md:p-10 rounded-[2rem] md:rounded-[3rem] space-y-8 shadow-2xl">
          <div className="space-y-4">
            <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block ml-2">
              Контент сообщения (HTML поддерживается)
            </label>
            <textarea
              className="w-full bg-black border border-zinc-800 rounded-3xl p-6 text-sm focus:border-blue-500 min-h-[250px] md:min-h-[350px] resize-none outline-none transition-all placeholder:text-zinc-800"
              placeholder={'Введите текст...\nПример: <b>Внимание!</b> Обновление системы.'}
              value={message}
              onChange={e => setMessage(e.target.value)}
              disabled={sending}
            />
          </div>

          <button
            onClick={handleSend}
            disabled={sending || !message || selectedBotIds.length === 0}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-5 rounded-2xl font-black uppercase tracking-widest text-xs transition-all shadow-xl shadow-blue-600/20 flex items-center justify-center gap-3"
          >
            {sending
              ? 'Процесс отправки...'
              : <><Send className="w-4 h-4" /> Запустить трансляцию</>
            }
          </button>
        </div>

        {/* Правая колонка — выбор ботов */}
        <div className="space-y-6">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest px-2 flex items-center justify-between">
            <span>Выберите ботов</span>
            <span className="text-blue-500">{selectedBotIds.length} выбрано</span>
          </h3>

          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-4 space-y-2 max-h-[500px] overflow-y-auto no-scrollbar shadow-xl">
            {broadcastEligible.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-6 text-center opacity-30">
                <AlertCircle className="w-8 h-8 mb-2" />
                <p className="text-[10px] uppercase font-bold">Нет активных ботов<br/>доступных для рассылки</p>
              </div>
            ) : (
              broadcastEligible.map(bot => {
                const meta = platformMeta(bot.platform);
                const selected = selectedBotIds.includes(bot.id);
                return (
                  <label
                    key={bot.id}
                    className={`flex items-center justify-between p-4 rounded-2xl cursor-pointer transition-all border ${
                      selected
                        ? 'bg-blue-600/10 border-blue-500/40 text-blue-400'
                        : 'bg-black border-zinc-900 hover:border-zinc-800 text-zinc-500'
                    }`}
                  >
                    <div className="flex items-center gap-3 truncate flex-1 min-w-0">
                      <span className="text-base shrink-0">{meta.icon}</span>
                      <div className="truncate">
                        <p className="text-xs font-bold truncate">{bot.name}</p>
                        <p className={`text-[9px] font-black uppercase ${meta.color}`}>{meta.badge}</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={selected}
                      onChange={() => toggleBot(bot.id)}
                    />
                    <div className={`w-5 h-5 rounded-lg border flex items-center justify-center shrink-0 transition-colors ml-2 ${
                      selected ? 'bg-blue-600 border-blue-600' : 'border-zinc-800'
                    }`}>
                      {selected && (
                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M5 13l4 4L19 7" strokeWidth="3" />
                        </svg>
                      )}
                    </div>
                  </label>
                );
              })
            )}
          </div>

          {/* Выбрать всех / снять */}
          {broadcastEligible.length > 0 && (
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedBotIds(broadcastEligible.map(b => b.id))}
                className="flex-1 py-2.5 text-[9px] font-black uppercase rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-white transition-all"
              >
                Выбрать все
              </button>
              <button
                onClick={() => setSelectedBotIds([])}
                className="flex-1 py-2.5 text-[9px] font-black uppercase rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-white transition-all"
              >
                Снять все
              </button>
            </div>
          )}

          <div className="p-5 bg-zinc-900/50 border border-zinc-800 rounded-3xl space-y-2">
            <p className="text-[9px] text-zinc-600 font-bold uppercase leading-relaxed text-center">
              Сообщение отправится только тем, кто не заблокировал бота
            </p>
            <p className="text-[9px] text-amber-700 font-bold uppercase text-center">
              ⚠️ Боты-постеры исключены из рассылки
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BroadcastManager;

import React, { useState } from 'react';
import { BotConfig } from '../types';
import { api } from '../services/apiService';
import { Send, CheckCircle2, AlertCircle, Bot as BotIcon, Image as ImageIcon, X } from 'lucide-react';

interface BroadcastManagerProps {
  bots: BotConfig[];
}

const BroadcastManager: React.FC<BroadcastManagerProps> = ({ bots }) => {
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{success: number, failed: number} | null>(null);
  const [photoUrl, setPhotoUrl] = useState('');

  const toggleBot = (id: string) => {
    setSelectedBotIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleImageUpload = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if(data.url) setPhotoUrl(data.url);
    } catch(e) {
        alert("Ошибка загрузки фото");
    }
  };

  const handleSend = async () => {
    if (!message || selectedBotIds.length === 0) return;
    setSending(true);
    setResult(null);
    try {
      // Важно: здесь мы передаем photoUrl в API. Убедись, что твой apiService пробрасывает этот аргумент
      // или передавай объект, если сигнатура метода позволяет.
      // Я предполагаю, что метод sendBroadcast нужно будет чуть подправить в apiService.ts
      // Но пока делаем вызов так, передавая данные в body запроса.
      
      // Если apiService жестко типизирован, тебе нужно добавить аргумент photoUrl в services/apiService.ts
      // Здесь я использую generic вызов как пример:
      const res = await api.sendBroadcast(selectedBotIds, message, photoUrl);
      
      if (res) {
        setResult(res);
        setMessage('');
        setPhotoUrl('');
        setSelectedBotIds([]);
      }
    } catch (e) {
      alert("Ошибка при выполнении рассылки");
    } finally {
      setSending(false);
    }
  };

  const activeBots = bots.filter(b => b.status === 'RUNNING');

  return (
    <div className="max-w-4xl mx-auto space-y-6 md:space-y-8 animate-in fade-in duration-500 pb-10">
      <header>
        <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight uppercase">Глобальная рассылка</h1>
        <p className="text-zinc-500 text-sm font-medium">Трансляция сообщений по всей базе пользователей выбранных узлов.</p>
      </header>

      {result && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-6 rounded-3xl flex items-center justify-between animate-in slide-in-from-top-4">
            <div className="flex items-center gap-4">
                <CheckCircle2 className="text-emerald-500 w-8 h-8" />
                <div>
                    <p className="text-white font-black text-sm uppercase">Рассылка завершена</p>
                    <p className="text-emerald-500/70 text-xs font-bold uppercase">Успешно: {result.success} | Ошибок: {result.failed}</p>
                </div>
            </div>
            <button onClick={() => setResult(null)} className="text-zinc-500 hover:text-white text-[10px] font-black uppercase">Закрыть</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
        <div className="md:col-span-2 bg-[#111] border border-zinc-800 p-6 md:p-10 rounded-[2rem] md:rounded-[3rem] space-y-8 shadow-2xl">
          <div className="space-y-4">
            <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block ml-2">Контент сообщения</label>
            <textarea 
              className="w-full bg-black border border-zinc-800 rounded-3xl p-6 text-sm focus:border-blue-500 min-h-[250px] md:min-h-[350px] resize-none outline-none transition-all placeholder:text-zinc-800"
              placeholder="Введите текст сообщения... HTML теги поддерживаются."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={sending}
            />
            
            {/* Блок добавления картинки */}
            <div className="flex items-center gap-4">
                <label className="cursor-pointer bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 px-5 py-3 rounded-xl flex items-center gap-2 transition-all">
                    <ImageIcon className="w-4 h-4 text-zinc-400" />
                    <span className="text-xs font-bold text-zinc-300">Прикрепить фото</span>
                    <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && handleImageUpload(e.target.files[0])} />
                </label>
                {photoUrl && (
                    <div className="flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 px-4 py-2 rounded-xl">
                        <span className="text-[10px] text-blue-400 font-bold uppercase">Фото загружено</span>
                        <button onClick={() => setPhotoUrl('')}><X className="w-4 h-4 text-blue-400 hover:text-white" /></button>
                    </div>
                )}
            </div>

          </div>
          <button 
            onClick={handleSend}
            disabled={sending || !message || selectedBotIds.length === 0}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-5 rounded-2xl font-black uppercase tracking-widest text-xs transition-all shadow-xl shadow-blue-600/20 flex items-center justify-center gap-3"
          >
            {sending ? 'Процесс отправки...' : <><Send className="w-4 h-4" /> Запустить трансляцию</>}
          </button>
        </div>

        <div className="space-y-6">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest px-2 flex items-center justify-between">
            <span>Выберите ботов</span>
            <span className="text-blue-500">{selectedBotIds.length} выбрано</span>
          </h3>
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-4 space-y-2 max-h-[500px] overflow-y-auto no-scrollbar shadow-xl">
            {activeBots.map(bot => (
              <label 
                key={bot.id} 
                className={`flex items-center justify-between p-4 rounded-2xl cursor-pointer transition-all border ${selectedBotIds.includes(bot.id) ? 'bg-blue-600/10 border-blue-500/40 text-blue-400' : 'bg-black border-zinc-900 hover:border-zinc-800 text-zinc-500'}`}
              >
                <div className="flex items-center gap-3 truncate">
                    <BotIcon className="w-4 h-4 shrink-0" />
                    <span className="text-xs font-bold truncate">{bot.name}</span>
                </div>
                <input type="checkbox" className="hidden" checked={selectedBotIds.includes(bot.id)} onChange={() => toggleBot(bot.id)} />
                <div className={`w-5 h-5 rounded-lg border flex items-center justify-center shrink-0 transition-colors ${selectedBotIds.includes(bot.id) ? 'bg-blue-600 border-blue-600' : 'border-zinc-800'}`}>
                  {selectedBotIds.includes(bot.id) && <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" strokeWidth="3" /></svg>}
                </div>
              </label>
            ))}
            {activeBots.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 px-6 text-center opacity-30">
                <AlertCircle className="w-8 h-8 mb-2" />
                <p className="text-[10px] uppercase font-bold">Нет активных (запущенных) ботов</p>
              </div>
            )}
          </div>
          <div className="p-6 bg-zinc-900/50 border border-zinc-800 rounded-3xl">
              <p className="text-[9px] text-zinc-600 font-bold uppercase leading-relaxed text-center">
                Сообщение будет отправлено только тем пользователям, которые не заблокировали бота
              </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BroadcastManager;

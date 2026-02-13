import React, { useState } from 'react';
import { Smartphone, Globe, X, Send, Shuffle } from 'lucide-react'; // Убедись, что lucide-react установлен

interface CreateBotModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Добавили platform в onSubmit
  onSubmit: (name: string, token: string, platform: 'telegram' | 'vk' | 'poster' | 'randomizer') => void;
}

const CreateBotModal: React.FC<CreateBotModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [platform, setPlatform] = useState<'telegram' | 'vk' | 'poster' | 'randomizer'>('telegram');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !token) return;
    
    // Передаем все три параметра
    onSubmit(name, token, platform);
    
    // Сброс состояния
    setName('');
    setToken('');
    setPlatform('telegram');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-[#121212] border border-zinc-800 rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-[#161616]">
          <div>
            <h2 className="text-xl font-bold text-white">Создать бота</h2>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1">Инициализация нового инстанса</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-800 rounded-full transition-colors text-zinc-500 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="space-y-5">
            
            {/* Выбор платформы */}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3 ml-1">Платформа</label>
              <div className="grid grid-cols-2 gap-3">
                {([
                  { id: 'telegram',   icon: <Smartphone className="w-4 h-4" />, label: 'TG Поддержка', color: 'blue' },
                  { id: 'vk',         icon: <Globe className="w-4 h-4" />,       label: 'VK Поддержка', color: 'blue' },
                  { id: 'poster',     icon: <Send className="w-4 h-4" />,         label: 'TG Постинг',   color: 'emerald' },
                  { id: 'randomizer', icon: <Shuffle className="w-4 h-4" />,      label: 'Рандомайзер',  color: 'purple' },
                ] as const).map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setPlatform(p.id as any)}
                    className={`flex items-center justify-center gap-2 p-3 rounded-2xl border transition-all ${
                      platform === p.id
                        ? p.color === 'emerald'
                          ? 'bg-emerald-600/10 border-emerald-500 text-emerald-400'
                          : p.color === 'purple'
                            ? 'bg-purple-600/10 border-purple-500 text-purple-400'
                            : 'bg-blue-600/10 border-blue-500 text-blue-400'
                        : 'bg-[#0a0a0a] border-zinc-800 text-zinc-500 hover:border-zinc-700'
                    }`}
                  >
                    {p.icon}
                    <span className="text-xs font-black uppercase">{p.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Имя бота */}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Название бота</label>
              <input
                type="text"
                required
                autoFocus
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:border-blue-500 focus:outline-none transition-all"
                placeholder={platform === 'vk' ? "Напр. Поддержка ВК" : "Напр. My Support Bot"}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            {/* Токен */}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2 ml-1">
                {platform === 'vk' ? 'Access Token (VK API)' : 'Bot Token (BotFather)'}
              </label>
              <input
                type="password"
                required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white font-mono focus:border-blue-500 focus:outline-none transition-all"
                placeholder={platform === 'vk' ? "vk1.a.xxxx..." : "123456789:AAF..."}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <p className="mt-3 text-[10px] text-zinc-500 leading-relaxed px-1">
                {platform === 'vk' 
                  ? "Токен можно получить в настройках сообщества: Работа с API → Ключи доступа." 
                  : "Получите этот токен у @BotFather в Telegram."}
              </p>
            </div>
          </div>

          {/* Кнопки действий */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest text-zinc-500 hover:bg-zinc-800 hover:text-white transition-all"
            >
              Отмена
            </button>
            <button
              type="submit"
              className="flex-[2] bg-blue-600 hover:bg-blue-500 text-white font-black text-[10px] uppercase tracking-widest py-4 rounded-2xl transition-all shadow-lg shadow-blue-600/20 active:scale-95"
            >
              Запустить инстанс
            </button>
          </div>
        </form>

        {/* Инфо-плашка */}
        <div className="bg-blue-500/5 p-4 border-t border-zinc-800">
             <p className="text-[9px] text-blue-500/50 uppercase font-bold text-center tracking-[0.2em]">
                System Ready • Policy 2026-02-09
             </p>
        </div>
      </div>
    </div>
  );
};

export default CreateBotModal;

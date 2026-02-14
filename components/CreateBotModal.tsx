import React, { useState } from 'react';
import { X, Bot } from 'lucide-react';

interface CreateBotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string, token: string) => void;
}

const CreateBotModal: React.FC<CreateBotModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [name,  setName]  = useState('');
  const [token, setToken] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !token.trim()) return;
    onSubmit(name.trim(), token.trim());
    setName('');
    setToken('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm bg-[#121212] border border-zinc-800 rounded-3xl shadow-2xl">

        {/* Шапка */}
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-[#161616] rounded-t-3xl">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center">
              <Bot className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <h2 className="text-base font-black text-white">Новый бот</h2>
              <p className="text-[9px] text-zinc-500 uppercase tracking-widest">Шаг 1 из 2 — добавление токена</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-800 rounded-full transition-colors text-zinc-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Форма */}
        <form id="cbf" onSubmit={handleSubmit} className="p-6 space-y-4">

          <div>
            <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">
              Название
            </label>
            <input
              type="text"
              required
              autoFocus
              className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:border-blue-500 outline-none transition-all"
              placeholder="Напр. Мой бот"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">
              Bot Token
            </label>
            <input
              type="password"
              required
              className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white font-mono focus:border-blue-500 outline-none transition-all"
              placeholder="123456789:AAF..."
              value={token}
              onChange={e => setToken(e.target.value)}
            />
            <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">
              Получить у @BotFather в Telegram или VK Access Token
            </p>
          </div>

          <div className="pt-1 p-4 bg-zinc-900/60 border border-zinc-800/60 rounded-2xl">
            <p className="text-[9px] text-zinc-500 leading-relaxed">
              После создания вы выберете тип бота (Поддержка / Постинг / Рандомайзер) и настроите его прямо в редакторе
            </p>
          </div>

        </form>

        {/* Кнопки */}
        <div className="p-6 pt-0 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-3.5 rounded-2xl font-black text-[10px] uppercase tracking-widest text-zinc-500 hover:bg-zinc-800 hover:text-white transition-all"
          >
            Отмена
          </button>
          <button
            type="submit"
            form="cbf"
            className="flex-[2] bg-blue-600 hover:bg-blue-500 text-white font-black text-[10px] uppercase tracking-widest py-3.5 rounded-2xl transition-all shadow-lg shadow-blue-600/20 active:scale-95"
          >
            Создать →
          </button>
        </div>

      </div>
    </div>
  );
};

export default CreateBotModal;

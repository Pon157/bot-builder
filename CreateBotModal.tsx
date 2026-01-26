
import React, { useState } from 'react';

interface CreateBotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string, token: string) => void;
}

const CreateBotModal: React.FC<CreateBotModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [name, setName] = useState('');
  const [token, setToken] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !token) return;
    onSubmit(name, token);
    setName('');
    setToken('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-[#121212] border border-zinc-800 rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center">
          <h2 className="text-xl font-bold text-white">Create New Bot</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Bot Name</label>
              <input
                type="text"
                required
                autoFocus
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                placeholder="e.g. My Support Bot"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Bot Token (from @BotFather)</label>
              <input
                type="password"
                required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white font-mono focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                placeholder="123456789:ABCdef..."
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <p className="mt-2 text-[10px] text-zinc-500">Get this token by messaging @BotFather on Telegram.</p>
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-3 rounded-xl font-bold text-sm text-zinc-400 hover:bg-zinc-800 transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-blue-600/20"
            >
              Initialize Bot
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateBotModal;

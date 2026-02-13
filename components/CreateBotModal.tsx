import React, { useState } from 'react';
import { Smartphone, Globe, X, Send, Shuffle, Hash, Users } from 'lucide-react';

type Platform = 'telegram' | 'vk' | 'poster' | 'randomizer';

interface CreateBotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (
    name: string,
    token: string,
    platform: Platform,
    extra: { adminIds?: number[]; channelId?: string; lotChannel?: string; botLink?: string }
  ) => void;
}

const PLATFORMS: { id: Platform; icon: React.ReactNode; label: string; active: string; hint: string }[] = [
  { id: 'telegram',   icon: <Smartphone className="w-4 h-4" />, label: 'TG Поддержка', active: 'bg-blue-600/10 border-blue-500 text-blue-400',    hint: 'Пересылает сообщения пользователей в группу/форум Telegram' },
  { id: 'vk',         icon: <Globe       className="w-4 h-4" />, label: 'VK Поддержка', active: 'bg-sky-600/10 border-sky-500 text-sky-400',       hint: 'Пересылает сообщения из VK-сообщества в беседу' },
  { id: 'poster',     icon: <Send        className="w-4 h-4" />, label: 'TG Постинг',   active: 'bg-emerald-600/10 border-emerald-500 text-emerald-400', hint: 'Публикует посты в Telegram-канал: текст, фото, видео, GIF, расписание, инлайн-кнопки' },
  { id: 'randomizer', icon: <Shuffle     className="w-4 h-4" />, label: 'Рандомайзер',  active: 'bg-purple-600/10 border-purple-500 text-purple-400',  hint: 'Честные розыгрыши с публикацией в канал, проверкой подписок и рассылкой' },
];

const CreateBotModal: React.FC<CreateBotModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [platform,    setPlatform]    = useState<Platform>('telegram');
  const [name,        setName]        = useState('');
  const [token,       setToken]       = useState('');
  const [adminIdsStr, setAdminIdsStr] = useState('');
  const [channelId,   setChannelId]   = useState('');
  const [lotChannel,  setLotChannel]  = useState('');
  const [botLink,     setBotLink]     = useState('');

  if (!isOpen) return null;

  const isPoster     = platform === 'poster';
  const isRandomizer = platform === 'randomizer';
  const isVK         = platform === 'vk';
  const selected     = PLATFORMS.find(p => p.id === platform)!;

  const parseAdminIds = (str: string): number[] =>
    str.split(',').map(s => s.trim()).filter(s => /^\d+$/.test(s)).map(Number);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !token.trim()) return;
    onSubmit(name.trim(), token.trim(), platform, {
      adminIds:   parseAdminIds(adminIdsStr),
      channelId:  channelId.trim()  || undefined,
      lotChannel: lotChannel.trim() || undefined,
      botLink:    botLink.trim()    || undefined,
    });
    setName(''); setToken(''); setAdminIdsStr('');
    setChannelId(''); setLotChannel(''); setBotLink('');
    setPlatform('telegram');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-[#121212] border border-zinc-800 rounded-3xl shadow-2xl flex flex-col max-h-[92vh]">

        {/* Шапка */}
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-[#161616] shrink-0 rounded-t-3xl">
          <div>
            <h2 className="text-xl font-bold text-white">Создать бота</h2>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Инициализация нового инстанса</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-800 rounded-full transition-colors text-zinc-500 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Тело */}
        <div className="overflow-y-auto no-scrollbar flex-1">
          <form id="cbf" onSubmit={handleSubmit} className="p-6 space-y-5">

            {/* Тип */}
            <div>
              <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-3 ml-1">Тип бота</label>
              <div className="grid grid-cols-2 gap-2">
                {PLATFORMS.map(p => (
                  <button key={p.id} type="button" onClick={() => setPlatform(p.id)}
                    className={`flex items-center justify-center gap-2 p-3 rounded-2xl border text-[11px] font-black uppercase transition-all ${
                      platform === p.id ? p.active : 'bg-[#0a0a0a] border-zinc-800 text-zinc-500 hover:border-zinc-700'
                    }`}>
                    {p.icon}{p.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[9px] text-zinc-600 ml-1 leading-relaxed">{selected.hint}</p>
            </div>

            {/* Название */}
            <div>
              <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">Название</label>
              <input type="text" required autoFocus
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:border-blue-500 outline-none transition-all"
                placeholder={isPoster ? 'Напр. Постинг @mychannel' : isRandomizer ? 'Напр. Розыгрыши' : isVK ? 'Напр. Поддержка ВКонтакте' : 'Напр. Support Bot'}
                value={name} onChange={e => setName(e.target.value)} />
            </div>

            {/* Токен */}
            <div>
              <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">
                {isVK ? 'Access Token (VK API)' : 'Bot Token (BotFather)'}
              </label>
              <input type="password" required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white font-mono focus:border-blue-500 outline-none transition-all"
                placeholder={isVK ? 'vk1.a.xxxx...' : '123456789:AAF...'}
                value={token} onChange={e => setToken(e.target.value)} />
              <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">
                {isVK ? 'Настройки сообщества → Работа с API → Ключи доступа' : 'Получить у @BotFather в Telegram'}
              </p>
            </div>

            {/* ID администраторов — для всех типов */}
            <div>
              <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1 flex items-center gap-1.5">
                <Users className="w-3 h-3 text-amber-500 shrink-0" />ID администраторов
              </label>
              <input type="text"
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:border-amber-500 outline-none transition-all"
                placeholder="123456789, 987654321"
                value={adminIdsStr} onChange={e => setAdminIdsStr(e.target.value)} />
              <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">
                {isPoster || isRandomizer ? 'Только эти пользователи могут управлять ботом' : 'Могут делать /broadcast прямо в боте'}
              </p>
            </div>

            {/* Канал — только постер */}
            {isPoster && (
              <div>
                <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1 flex items-center gap-1.5">
                  <Hash className="w-3 h-3 text-emerald-500 shrink-0" />Канал для публикации
                </label>
                <input type="text"
                  className="w-full bg-[#0a0a0a] border border-emerald-900/40 rounded-2xl p-4 text-sm text-white focus:border-emerald-500 outline-none transition-all"
                  placeholder="@mychannel или -1001234567890"
                  value={channelId} onChange={e => setChannelId(e.target.value)} />
                <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">Бот должен быть администратором канала</p>
              </div>
            )}

            {/* Канал + ссылка — только рандомайзер */}
            {isRandomizer && (<>
              <div>
                <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1 flex items-center gap-1.5">
                  <Hash className="w-3 h-3 text-purple-500 shrink-0" />Канал розыгрышей
                </label>
                <input type="text"
                  className="w-full bg-[#0a0a0a] border border-purple-900/40 rounded-2xl p-4 text-sm text-white focus:border-purple-500 outline-none transition-all"
                  placeholder="@lotchannel или -1001234567890"
                  value={lotChannel} onChange={e => setLotChannel(e.target.value)} />
                <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">Сюда публикуются посты розыгрышей. Бот — администратор.</p>
              </div>
              <div>
                <label className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">
                  Username бота (для ссылок)
                </label>
                <input type="text"
                  className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:border-purple-500 outline-none transition-all"
                  placeholder="@MyLotteryBot"
                  value={botLink} onChange={e => setBotLink(e.target.value)} />
                <p className="mt-1.5 text-[9px] text-zinc-600 ml-1">Для генерации deep-link ссылок участия</p>
              </div>
            </>)}

          </form>
        </div>

        {/* Кнопки */}
        <div className="p-6 border-t border-zinc-800 shrink-0 flex gap-3 rounded-b-3xl bg-[#121212]">
          <button type="button" onClick={onClose}
            className="flex-1 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest text-zinc-500 hover:bg-zinc-800 hover:text-white transition-all">
            Отмена
          </button>
          <button type="submit" form="cbf"
            className="flex-[2] bg-blue-600 hover:bg-blue-500 text-white font-black text-[10px] uppercase tracking-widest py-4 rounded-2xl transition-all shadow-lg shadow-blue-600/20 active:scale-95">
            Запустить инстанс
          </button>
        </div>

      </div>
    </div>
  );
};

export default CreateBotModal;

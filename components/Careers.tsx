import React, { useState } from 'react';
import {
  ArrowLeft, ArrowRight, Briefcase, Star, Zap, Users,
  Code2, Megaphone, X, CheckCircle, ChevronDown, ChevronUp, Send
} from 'lucide-react';

// ── Типы ────────────────────────────────────────────────────────
interface Vacancy {
  id: string;
  icon: React.ElementType;
  color: string;
  glow: string;
  pill: string;
  pillBg: string;
  badge: string;
  title: string;
  short: string;
  pay: string;
  payNote: string;
  tasks: string[];
  requirements: string[];
}

interface AppForm {
  vacancy_id: string;
  vacancy_title: string;
  contact: string;
  experience: string;
  about: string;
  extra: string;
}

// ── Данные вакансий ─────────────────────────────────────────────
const VACANCIES: Vacancy[] = [
  {
    id: 'smm',
    icon: Megaphone,
    color: 'text-sky-400',
    glow: 'shadow-sky-500/20',
    pill: 'text-sky-400 border-sky-500/30',
    pillBg: 'bg-sky-500/10',
    badge: 'Договорная оплата',
    title: 'SMM / Монтажёр / Пиар в чатах',
    short: 'Контент, видео, продвижение в соцсетях и Telegram-чатах',
    pay: 'Договорная',
    payNote: 'Обсуждается индивидуально на собеседовании',
    tasks: [
      'Создание и оформление контента для Telegram и VK',
      'Видеомонтаж коротких роликов, Reels, shorts',
      'Размещение рекламных сообщений в тематических чатах',
      'Ведение и раскрутка соцсетей команды',
      'Генерация идей для продвижения продукта',
    ],
    requirements: [
      'Опыт в SMM, монтаже или пиаре от 2–3 месяцев',
      'Умение работать с CapCut / Premiere / DaVinci (для монтажёров)',
      'Понимание трендов и форматов контента',
      'Активность в Telegram-чатах — плюс',
      'Ответственность и соблюдение дедлайнов',
    ],
  },
  {
    id: 'outreach',
    icon: Users,
    color: 'text-violet-400',
    glow: 'shadow-violet-500/20',
    pill: 'text-violet-400 border-violet-500/30',
    pillBg: 'bg-violet-500/10',
    badge: '15–30 звезд за клиента',
    title: 'Специалист по привлечению клиентов',
    short: 'Переманивать владельцев ботов на наш конструктор',
    pay: '15–30 звезд за клиента',
    payNote: 'Зависит от суммы покупки ключа клиентом. Бонусы за объём.',
    tasks: [
      'Поиск владельцев ботов, работающих не на нашем конструкторе',
      'Написание им с предложением перейти на Dialoge Engine',
      'Ведение диалога от первого контакта до покупки ключа',
      'Отчётность по обработанным лидам',
      'Работа с базой: Telegram-боты, VK-сообщества, форумы',
    ],
    requirements: [
      'Умение вести переговоры и убеждать',
      'Базовое понимание Telegram / VK ботов',
      'Настойчивость и системный подход',
      'Хороший Telegram-аккаунт с историей',
      'Умение грамотно писать — обязательно',
    ],
  },
  {
    id: 'tech',
    icon: Code2,
    color: 'text-emerald-400',
    glow: 'shadow-emerald-500/20',
    pill: 'text-emerald-400 border-emerald-500/30',
    pillBg: 'bg-emerald-500/10',
    badge: 'Создание ботов на заказ',
    title: 'Технический администратор ботов',
    short: 'Настройка и запуск ботов клиентов через наш конструктор',
    pay: 'Фиксированная ставка за каждый бот',
    payNote: 'Ставка за настроенный бот обсуждается отдельно',
    tasks: [
      'Настройка и запуск ботов клиентов через наш конструктор',
      'Подключение кнопок, триггеров, приветствий, ИИ-ассистента',
      'Техническая поддержка клиентов после запуска',
      'Написание мини-инструкций по настройке',
      'Тестирование функционала перед сдачей',
    ],
    requirements: [
      'Опыт работы с Telegram / VK ботами',
      'Понимание webhook, токенов, peer_id',
      'Внимательность к деталям конфигурации',
      'Умение объяснять технические вещи простым языком',
      'Желание разобраться в нашем стеке быстро',
    ],
  },
];

const EMPTY_FORM: AppForm = {
  vacancy_id: '',
  vacancy_title: '',
  contact: '',
  experience: '',
  about: '',
  extra: '',
};

// ── Компонент ───────────────────────────────────────────────────
const Careers: React.FC = () => {
  const [openId, setOpenId]   = useState<string | null>(null);
  const [modalId, setModalId] = useState<string | null>(null);
  const [form, setForm]       = useState<AppForm>(EMPTY_FORM);
  const [sending, setSending] = useState(false);
  const [sent, setSent]       = useState(false);

  const activeVacancy = VACANCIES.find(v => v.id === modalId);

  const openApply = (v: Vacancy) => {
    setForm({ ...EMPTY_FORM, vacancy_id: v.id, vacancy_title: v.title });
    setSent(false);
    setModalId(v.id);
  };

  const closeModal = () => { setModalId(null); setSent(false); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    try {
      const base = (window as any).__API_BASE__ || '/api';
      const res = await fetch(`${base}/applications/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setSent(true);
      } else {
        alert('Ошибка при отправке. Попробуйте позже.');
      }
    } catch {
      alert('Нет связи с сервером.');
    } finally {
      setSending(false);
    }
  };

  const field = (key: keyof AppForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value }));

  return (
    <div className="min-h-screen bg-[#030a18] text-slate-300 font-sans selection:bg-blue-900 selection:text-white">

      {/* ── AMBIENT ────────────────────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-60 -left-60 w-[700px] h-[700px] bg-blue-700/8 rounded-full blur-[160px]" />
        <div className="absolute top-1/2 -right-40 w-[500px] h-[500px] bg-indigo-700/6 rounded-full blur-[140px]" />
        <div className="absolute bottom-0 left-1/3 w-[400px] h-[400px] bg-cyan-700/5 rounded-full blur-[120px]" />
      </div>

      {/* ── HERO ─────────────────────────────────────────────────── */}
      <div className="relative z-10 border-b border-slate-800/50">
        <div className="max-w-5xl mx-auto px-5 sm:px-8 py-16 md:py-24">

          <a href="/"
            className="inline-flex items-center gap-2 text-slate-600 hover:text-slate-300 text-[10px] font-black uppercase tracking-[0.2em] transition-colors mb-14 group"
          >
            <ArrowLeft className="w-3 h-3 group-hover:-translate-x-1 transition-transform" />
            Главная
          </a>

          <div className="flex flex-wrap items-center gap-3 mb-7">
            <div className="w-11 h-11 rounded-xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-600/30">
              <Briefcase className="w-5 h-5 text-white" />
            </div>
            <span className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-400 bg-blue-500/10 border border-blue-500/20 px-3 py-1.5 rounded-full">
              Открытые позиции · {VACANCIES.length}
            </span>
          </div>

          <h1 className="text-4xl md:text-[3.5rem] font-black text-white tracking-tight leading-none mb-5">
            Работай с нами.<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-400 to-violet-400">
              Строй продукт.
            </span>
          </h1>

          <p className="text-slate-400 text-base md:text-lg max-w-xl leading-relaxed">
            Dialoge Engine растёт — нам нужны люди с инициативой. Удалёнка, свободный график.
          </p>

          <div className="mt-10 flex flex-wrap gap-8">
            {[
              { icon: Star,  label: 'Полностью удалённо' },
              { icon: Zap,   label: 'Свободный график'       },
              { icon: Users, label: 'Маленькая живая команда' },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-2 text-slate-500 text-sm">
                <Icon className="w-4 h-4 text-blue-500 shrink-0" /> {label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── СПИСОК ВАКАНСИЙ ──────────────────────────────────────── */}
      <div className="relative z-10 max-w-5xl mx-auto px-5 sm:px-8 py-14 space-y-4">

        {VACANCIES.map(v => {
          const Icon  = v.icon;
          const isOpen = openId === v.id;

          return (
            <div
              key={v.id}
              className={`rounded-2xl border border-slate-800/80 bg-[#080f1f]/80 backdrop-blur-sm overflow-hidden transition-all duration-300 hover:border-slate-700`}
            >
              {/* Header */}
              <button
                className="w-full text-left px-7 py-6 flex items-start gap-5 group"
                onClick={() => setOpenId(isOpen ? null : v.id)}
              >
                <div className={`w-12 h-12 rounded-xl bg-slate-900 border border-slate-700/50 flex items-center justify-center shrink-0 ${v.color} shadow-lg ${v.glow}`}>
                  <Icon className="w-5 h-5" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <h2 className="text-base font-black text-white">{v.title}</h2>
                    <span className={`text-[9px] font-black uppercase px-2.5 py-0.5 rounded-full border ${v.pill} ${v.pillBg}`}>
                      {v.badge}
                    </span>
                  </div>
                  <p className="text-slate-500 text-sm">{v.short}</p>
                </div>

                <div className={`shrink-0 transition-colors mt-1 ${isOpen ? v.color : 'text-slate-700 group-hover:text-slate-400'}`}>
                  {isOpen ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </div>
              </button>

              {/* Expanded */}
              {isOpen && (
                <div className="px-7 pb-8 space-y-6 animate-in fade-in slide-in-from-top-1 duration-200">
                  <div className="h-px bg-slate-800/80" />

                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <p className="text-[9px] font-black text-slate-600 uppercase tracking-[0.2em] mb-3">Задачи</p>
                      <ul className="space-y-2.5">
                        {v.tasks.map((t, i) => (
                          <li key={i} className="flex gap-3 text-sm text-slate-300 leading-relaxed">
                            <span className={`mt-[7px] w-1 h-1 rounded-full shrink-0 bg-current ${v.color}`} />
                            {t}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-[9px] font-black text-slate-600 uppercase tracking-[0.2em] mb-3">Требования</p>
                      <ul className="space-y-2.5">
                        {v.requirements.map((r, i) => (
                          <li key={i} className="flex gap-3 text-sm text-slate-300 leading-relaxed">
                            <span className={`mt-[7px] w-1 h-1 rounded-full shrink-0 bg-current ${v.color}`} />
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Оплата */}
                  <div className="flex items-center gap-4 bg-slate-900/60 border border-slate-800 rounded-xl px-5 py-4">
                    <div className={`text-xl font-black ${v.color}`}>{v.pay}</div>
                    <div className="h-7 w-px bg-slate-800" />
                    <p className="text-slate-500 text-xs leading-relaxed">{v.payNote}</p>
                  </div>

                  <button
                    onClick={() => openApply(v)}
                    className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white font-bold text-sm px-6 py-3.5 rounded-xl transition-all shadow-lg shadow-blue-600/20"
                  >
                    <Send className="w-4 h-4" />
                    Откликнуться
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── CTA ──────────────────────────────────────────────────── */}
      <div className="relative z-10 max-w-5xl mx-auto px-5 sm:px-8 pb-24">
        <div className="border border-blue-500/15 bg-blue-600/4 rounded-2xl px-8 py-10 text-center">
          <p className="text-slate-600 text-[10px] font-black uppercase tracking-[0.2em] mb-2">
            Не нашли подходящего?
          </p>
          <h3 className="text-xl font-black text-white mb-5">Напишите нам напрямую</h3>
          <a
            href="https://t.me/Kotickr"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white text-sm font-bold px-6 py-3 rounded-xl transition-all"
          >
            @Kotickr в Telegram <ArrowRight className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* ── МОДАЛ ОТКЛИКА ────────────────────────────────────────── */}
      {modalId && activeVacancy && (
        <div
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={e => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <div className="w-full max-w-lg bg-[#080f1f] border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col">

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center ${activeVacancy.color}`}>
                  <activeVacancy.icon className="w-4 h-4" />
                </div>
                <div>
                  <p className="text-white font-black text-sm leading-tight">{activeVacancy.title}</p>
                  <p className="text-slate-600 text-[10px] uppercase tracking-wider">Отклик на вакансию</p>
                </div>
              </div>
              <button
                onClick={closeModal}
                className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-all"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Успех */}
            {sent ? (
              <div className="flex flex-col items-center justify-center gap-4 py-16 px-8 text-center">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                  <CheckCircle className="w-8 h-8 text-emerald-400" />
                </div>
                <h3 className="text-white font-black text-xl">Отклик отправлен!</h3>
                <p className="text-slate-400 text-sm max-w-xs leading-relaxed">
                  Мы рассмотрим вашу заявку и свяжемся с вами по указанному контакту в ближайшее время.
                </p>
                <button
                  onClick={closeModal}
                  className="mt-2 px-6 py-3 bg-slate-800 hover:bg-slate-700 text-white text-sm font-bold rounded-xl transition-all"
                >
                  Закрыть
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">

                {/* Контакт */}
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-[0.15em] mb-1.5">
                    Контакт для связи *
                  </label>
                  <input
                    required
                    value={form.contact}
                    onChange={field('contact')}
                    placeholder="@username в Telegram, email, ВКонтакте..."
                    className="w-full bg-black/60 border border-slate-700 focus:border-blue-500 p-3.5 rounded-xl text-white text-sm outline-none transition-all placeholder:text-slate-700"
                  />
                </div>

                {/* Опыт */}
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-[0.15em] mb-1.5">
                    Ваш опыт в этой сфере *
                  </label>
                  <input
                    required
                    value={form.experience}
                    onChange={field('experience')}
                    placeholder="Например: 1 год SMM в TikTok + монтаж"
                    className="w-full bg-black/60 border border-slate-700 focus:border-blue-500 p-3.5 rounded-xl text-white text-sm outline-none transition-all placeholder:text-slate-700"
                  />
                </div>

                {/* О себе */}
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-[0.15em] mb-1.5">
                    Расскажите о себе — ваши сильные стороны *
                  </label>
                  <textarea
                    required
                    rows={4}
                    value={form.about}
                    onChange={field('about')}
                    placeholder="Что умеете, чем гордитесь, почему хотите работать с нами..."
                    className="w-full bg-black/60 border border-slate-700 focus:border-blue-500 p-3.5 rounded-xl text-white text-sm outline-none transition-all resize-none placeholder:text-slate-700"
                  />
                </div>

                {/* Доп */}
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-[0.15em] mb-1.5">
                    Портфолио, ссылки, примеры работ (опционально)
                  </label>
                  <textarea
                    rows={2}
                    value={form.extra}
                    onChange={field('extra')}
                    placeholder="GitHub, канал, проекты, примеры работ..."
                    className="w-full bg-black/60 border border-slate-700 focus:border-blue-500 p-3.5 rounded-xl text-white text-sm outline-none transition-all resize-none placeholder:text-slate-700"
                  />
                </div>

                <button
                  type="submit"
                  disabled={sending}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 active:scale-[0.99] text-white font-black py-4 rounded-xl text-sm uppercase tracking-widest transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2"
                >
                  {sending ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Отправляем...
                    </>
                  ) : (
                    <><Send className="w-4 h-4" /> Отправить отклик</>
                  )}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Careers;

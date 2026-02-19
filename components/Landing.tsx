import React, { useState } from 'react';
import { MessageSquare, Zap, BarChart3, Send, ArrowRight, Star, ExternalLink, X, PlusCircle } from 'lucide-react';

const Landing = () => {
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [reviewForm, setReviewForm] = useState({ name: '', role: '', text: '', rating: 5 });

  const features = [
    {
      icon: <MessageSquare className="w-6 h-6" />,
      title: "Простой конструктор триггеров",
      description: "Создавайте сложные сценарии без программирования"
    },
    {
      icon: <Zap className="w-6 h-6" />,
      title: "Отправка в обычные и топик-чаты",
      description: "Гибкая маршрутизация сообщений"
    },
    {
      icon: <BarChart3 className="w-6 h-6" />,
      title: "Полная статистика с графиками",
      description: "Аналитика в реальном времени"
    },
    {
      icon: <Send className="w-6 h-6" />,
      title: "Массовые рассылки на ботов",
      description: "Эффективный инструмент коммуникации"
    }
  ];

  const partners = [
    {
      name: "NOVA Creators",
      url: "https://t.me/NOVA_creators",
      initial: "N",
      description: "Креативная студия нового поколения"
    }
  ];

  // Здесь в будущем ты будешь делать fetch() из базы данных (только status = 'approved')
  const reviews = [
    {
      author: "@Fopertion",
      role: "Владелец ИИ-бота (@Alia_Nova_Bot)",
      text: "Создание ИИ через DialogEngine — это по-настоящему имба. Интерфейс понятный даже новичку, нет необходимости писать сложный код. Боты работают быстро и корректно, задержек почти нет. Отдельный плюс за гибкую настройку поведения ИИ.",
      rating: 5
    }
  ];

  const team = [
    { name: "Kotickr", role: "Разработчик + Владелец", telegram: "https://t.me/Kotickr" },
    { name: "Gift Relayers", role: "Директор", telegram: "https://t.me/giftrelayers" }
  ];

  const handleReviewSubmit = (e) => {
    e.preventDefault();
    // TODO: Здесь будет fetch запрос на твой API
    console.log("Отправка на модерацию:", reviewForm);
    alert("Спасибо! Отзыв отправлен на модерацию администратору.");
    setIsReviewModalOpen(false);
    setReviewForm({ name: '', role: '', text: '', rating: 5 });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300 font-sans selection:bg-blue-900 selection:text-white">
      
      {/* --- HERO SECTION --- */}
      <div className="relative border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-24 lg:py-32 flex flex-col items-center text-center">
          <div className="w-20 h-20 bg-blue-600 rounded flex items-center justify-center mb-8">
            <MessageSquare className="w-10 h-10 text-white" strokeWidth={2} />
          </div>
          
          <h1 className="text-4xl md:text-6xl font-bold text-white tracking-tight mb-6">
            DialogEngine. <br/>
            <span className="text-blue-500">Корпоративные боты</span> нового поколения.
          </h1>
          
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mb-10">
            Мощный конструктор для бизнеса: триггеры, кнопки, рассылки и сквозная аналитика в строгом интерфейсе.
          </p>

          <a href="/auth" className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-medium text-lg px-8 py-4 transition-colors">
            Начать работу
            <ArrowRight className="w-5 h-5" />
          </a>
        </div>
      </div>

      {/* --- FEATURES SECTION --- */}
      <div className="py-20 border-b border-slate-800 bg-slate-900/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="grid md:grid-cols-2 gap-6">
            {features.map((feature, i) => (
              <div key={i} className="p-8 border border-slate-800 bg-slate-950 hover:border-blue-500/50 transition-colors">
                <div className="text-blue-500 mb-4">{feature.icon}</div>
                <h3 className="font-semibold text-xl text-white mb-2">{feature.title}</h3>
                <p className="text-slate-400 leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --- REVIEWS SECTION --- */}
      <div className="py-20 border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="flex flex-col md:flex-row justify-between items-center mb-12 gap-4">
            <h2 className="text-3xl font-bold text-white tracking-tight">Отзывы клиентов</h2>
            <button 
              onClick={() => setIsReviewModalOpen(true)}
              className="inline-flex items-center gap-2 px-6 py-3 border border-blue-600 text-blue-500 hover:bg-blue-600 hover:text-white transition-colors text-sm font-medium"
            >
              <PlusCircle className="w-4 h-4" />
              Оставить отзыв
            </button>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {reviews.map((review, i) => (
              <div key={i} className="p-8 border border-slate-800 bg-slate-900/50 flex flex-col justify-between">
                <div>
                  <div className="flex gap-1 mb-4">
                    {[...Array(review.rating)].map((_, j) => (
                      <Star key={j} className="w-4 h-4 fill-blue-500 text-blue-500" />
                    ))}
                  </div>
                  <p className="text-slate-300 mb-6 leading-relaxed text-sm">"{review.text}"</p>
                </div>
                <div className="border-t border-slate-800 pt-4 mt-4">
                  <p className="font-semibold text-white">{review.author}</p>
                  <p className="text-sm text-slate-500">{review.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --- PARTNERS & TEAM SECTION --- */}
      <div className="py-20 bg-slate-900/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="grid md:grid-cols-2 gap-12">
            
            {/* Partners */}
            <div>
              <h2 className="text-2xl font-bold text-white mb-8">Партнёры</h2>
              <div className="space-y-4">
                {partners.map((partner, i) => (
                  <a key={i} href={partner.url} target="_blank" rel="noopener noreferrer" 
                     className="block p-6 border border-slate-800 bg-slate-950 hover:border-blue-500/50 transition-colors group">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-blue-900/30 text-blue-500 flex items-center justify-center font-bold text-xl border border-blue-900/50">
                        {partner.initial}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-white flex items-center gap-2">
                          {partner.name}
                          <ExternalLink className="w-3 h-3 text-slate-600 group-hover:text-blue-500" />
                        </h3>
                        <p className="text-sm text-slate-400">{partner.description}</p>
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </div>

            {/* Team */}
            <div>
              <h2 className="text-2xl font-bold text-white mb-8">Команда</h2>
              <div className="space-y-4">
                {team.map((member, i) => (
                  <a key={i} href={member.telegram} target="_blank" rel="noopener noreferrer" 
                     className="block p-6 border border-slate-800 bg-slate-950 hover:border-blue-500/50 transition-colors group">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-slate-800 text-slate-300 flex items-center justify-center font-bold text-xl">
                        {member.name[0]}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-white flex items-center gap-2">
                          {member.name}
                          <ExternalLink className="w-3 h-3 text-slate-600 group-hover:text-blue-500" />
                        </h3>
                        <p className="text-sm text-slate-400">{member.role}</p>
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* --- FOOTER --- */}
      <footer className="py-8 border-t border-slate-800 bg-slate-950">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-slate-500 text-sm">
            © 2026 DialogEngine. Все права защищены.
          </p>
        </div>
      </footer>

      {/* --- MODAL (REVIEW FORM) --- */}
      {isReviewModalOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-lg p-6 relative shadow-2xl">
            <button 
              onClick={() => setIsReviewModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            
            <h3 className="text-xl font-bold text-white mb-6">Оставить отзыв</h3>
            
            <form onSubmit={handleReviewSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Ваше имя / Telegram</label>
                <input 
                  type="text" required
                  value={reviewForm.name}
                  onChange={(e) => setReviewForm({...reviewForm, name: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-700 p-3 text-white focus:outline-none focus:border-blue-500"
                  placeholder="@username"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Роль / Проект</label>
                <input 
                  type="text" required
                  value={reviewForm.role}
                  onChange={(e) => setReviewForm({...reviewForm, role: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-700 p-3 text-white focus:outline-none focus:border-blue-500"
                  placeholder="Владелец ИИ-бота"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Отзыв</label>
                <textarea 
                  required rows={4}
                  value={reviewForm.text}
                  onChange={(e) => setReviewForm({...reviewForm, text: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-700 p-3 text-white focus:outline-none focus:border-blue-500 resize-none"
                  placeholder="Опишите ваш опыт работы с платформой..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Оценка (1-5)</label>
                <input 
                  type="number" min="1" max="5" required
                  value={reviewForm.rating}
                  onChange={(e) => setReviewForm({...reviewForm, rating: parseInt(e.target.value)})}
                  className="w-full bg-slate-950 border border-slate-700 p-3 text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <button 
                type="submit"
                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-3 mt-4 transition-colors"
              >
                Отправить на проверку
              </button>
            </form>
          </div>
        </div>
      )}
      
    </div>
  );
};

export default Landing;

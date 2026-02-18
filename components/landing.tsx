import React, { useState, useEffect } from 'react';
import { MessageSquare, Zap, BarChart3, Send, ArrowRight, Star, ExternalLink } from 'lucide-react';

const Landing = () => {
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => setScrollY(window.scrollY);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const features = [
    {
      icon: <MessageSquare className="w-8 h-8" />,
      title: "Простой конструктор триггеров",
      description: "Создавайте сложные сценарии без программирования"
    },
    {
      icon: <Zap className="w-8 h-8" />,
      title: "Отправка в обычные и топик-чаты",
      description: "Гибкая маршрутизация сообщений"
    },
    {
      icon: <BarChart3 className="w-8 h-8" />,
      title: "Полная статистика с графиками",
      description: "Аналитика в реальном времени"
    },
    {
      icon: <Send className="w-8 h-8" />,
      title: "Массовые рассылки на ботов",
      description: "Эффективный инструмент коммуникации"
    }
  ];

  const partners = [
    {
      name: "NOVA Creators",
      url: "https://t.me/NOVA_creators",
      logo: "/nova.png",
      description: "Креативная студия нового поколения"
    }
  ];

  const reviews = [
    {
      author: "Александр К.",
      role: "CEO стартапа",
      text: "Dialoge Engine полностью изменил нашу коммуникацию с клиентами. Простой интерфейс, мощная аналитика — всё что нужно!",
      rating: 5
    },
    {
      author: "Мария С.",
      role: "Маркетолог",
      text: "Лучший конструктор для корпоративных ботов. Настроили триггеры за 15 минут, рассылки работают как часы.",
      rating: 5
    },
    {
      author: "Дмитрий Р.",
      role: "Product Manager",
      text: "Статистика в реальном времени помогла нам оптимизировать поддержку. Рекомендую всем командам!",
      rating: 5
    }
  ];

  const team = [
    {
      name: "Kotickr",
      role: "Разработчик + Владелец",
      telegram: "https://t.me/Kotickr"
    },
    {
      name: "Gift Relayers",
      role: "Директор",
      telegram: "https://t.me/giftrelayers"
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-green-900 to-gray-900 text-white overflow-hidden">
      {/* Hero Section */}
      <div className="relative min-h-screen flex items-center justify-center px-6">
        {/* Animated Background Particles */}
        <div className="absolute inset-0 overflow-hidden">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="absolute rounded-full bg-green-400 opacity-20 animate-float"
              style={{
                width: Math.random() * 100 + 50 + 'px',
                height: Math.random() * 100 + 50 + 'px',
                left: Math.random() * 100 + '%',
                top: Math.random() * 100 + '%',
                animationDelay: Math.random() * 5 + 's',
                animationDuration: Math.random() * 10 + 10 + 's'
              }}
            />
          ))}
        </div>

        {/* Main Content */}
        <div className="relative z-10 max-w-6xl mx-auto text-center">
          {/* Logo */}
          <div 
            className="mb-12 inline-block transition-transform duration-700"
            style={{ transform: `translateY(${scrollY * 0.3}px)` }}
          >
            <div className="w-64 h-64 mx-auto bg-gradient-to-br from-green-400 to-green-600 rounded-3xl shadow-2xl flex items-center justify-center animate-pulse-slow">
              <div className="w-48 h-48 border-8 border-white/30 rounded-2xl flex items-center justify-center">
                <MessageSquare className="w-32 h-32 text-white" strokeWidth={1.5} />
              </div>
            </div>
          </div>

          {/* Headline */}
          <h1 className="text-6xl md:text-7xl font-black mb-6 bg-clip-text text-transparent bg-gradient-to-r from-white via-green-200 to-white animate-gradient">
            Dialoge Engine — корпоративные боты нового поколения
          </h1>

          <p className="text-xl md:text-2xl text-gray-300 mb-12 max-w-4xl mx-auto leading-relaxed">
            Мощный конструктор для бизнеса: триггеры, Keyboard-кнопки, рассылки и аналитика в реальном времени.
          </p>

          {/* Feature Grid */}
          <div className="grid md:grid-cols-2 gap-6 mb-12 max-w-4xl mx-auto">
            {features.map((feature, i) => (
              <div 
                key={i}
                className="bg-black/40 backdrop-blur-lg border border-green-500/20 rounded-2xl p-6 text-left hover:border-green-500/40 transition-all duration-300 hover:scale-105"
              >
                <div className="text-green-400 mb-3">{feature.icon}</div>
                <h3 className="font-bold text-xl mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-sm">{feature.description}</p>
              </div>
            ))}
          </div>

          {/* CTA Button */}
          <a 
            href="/auth"
            className="inline-flex items-center gap-3 bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white font-black text-lg px-12 py-5 rounded-full shadow-2xl transition-all duration-300 hover:scale-110 hover:shadow-green-500/50"
          >
            Подключиться / Узнать больше
            <ArrowRight className="w-6 h-6" />
          </a>

          <p className="mt-6 text-gray-500 text-sm">
            Команда: <a href="https://t.me/Kotickr" target="_blank" rel="noopener noreferrer" className="text-green-400 hover:underline">@kotickr</a>, <a href="https://t.me/mrakotik" target="_blank" rel="noopener noreferrer" className="text-green-400 hover:underline">@mrakotik</a> + #HWM
          </p>
        </div>
      </div>

      {/* Partners Section */}
      <div className="py-20 px-6 bg-black/30 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-black text-center mb-12">Наши партнёры</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {partners.map((partner, i) => (
              <a
                key={i}
                href={partner.url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-2xl p-8 text-center hover:scale-105 transition-all duration-300 border border-green-500/20 hover:border-green-500/60 group"
              >
                <div className="w-24 h-24 mx-auto mb-6 rounded-full overflow-hidden border-4 border-green-500/40 group-hover:border-green-500">
                  <img src={partner.logo} alt={partner.name} className="w-full h-full object-cover" />
                </div>
                <h3 className="font-bold text-xl mb-2 group-hover:text-green-400 transition-colors">{partner.name}</h3>
                <p className="text-gray-400 text-sm mb-4">{partner.description}</p>
                <ExternalLink className="w-5 h-5 mx-auto text-green-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Reviews Section */}
      <div className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-black text-center mb-12">Отзывы клиентов</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {reviews.map((review, i) => (
              <div
                key={i}
                className="bg-black/40 backdrop-blur-lg border border-green-500/20 rounded-2xl p-6 hover:border-green-500/40 transition-all duration-300"
              >
                <div className="flex gap-1 mb-4">
                  {[...Array(review.rating)].map((_, j) => (
                    <Star key={j} className="w-5 h-5 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-300 mb-6 italic">"{review.text}"</p>
                <div className="border-t border-gray-700 pt-4">
                  <p className="font-bold">{review.author}</p>
                  <p className="text-sm text-gray-500">{review.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Team Section */}
      <div className="py-20 px-6 bg-black/30 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-black text-center mb-12">Наша команда</h2>
          <div className="grid md:grid-cols-2 gap-8">
            {team.map((member, i) => (
              <a
                key={i}
                href={member.telegram}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-2xl p-8 text-center hover:scale-105 transition-all duration-300 border border-green-500/20 hover:border-green-500/60 group"
              >
                <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center text-4xl font-black">
                  {member.name[0]}
                </div>
                <h3 className="font-bold text-xl mb-2 group-hover:text-green-400 transition-colors">{member.name}</h3>
                <p className="text-gray-400 text-sm mb-4">{member.role}</p>
                <ExternalLink className="w-5 h-5 mx-auto text-green-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-12 px-6 border-t border-gray-800">
        <div className="max-w-6xl mx-auto text-center">
          <p className="text-gray-500">
            © 2025 Dialoge Engine. Корпоративные боты нового поколения.
          </p>
          <p className="text-gray-600 text-sm mt-2">
            Создано с 💚 командой <a href="https://t.me/Kotickr" className="text-green-400 hover:underline">Kotickr</a>
          </p>
        </div>
      </footer>

      <style jsx>{`
        @keyframes float {
          0%, 100% { transform: translateY(0) translateX(0); }
          50% { transform: translateY(-20px) translateX(10px); }
        }
        .animate-float {
          animation: float linear infinite;
        }
        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient 5s ease infinite;
        }
        @keyframes pulse-slow {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.05); }
        }
        .animate-pulse-slow {
          animation: pulse-slow 4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
};

export default Landing;

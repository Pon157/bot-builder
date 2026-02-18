import React from 'react';
import { MessageSquare, Zap, BarChart3, Send, ArrowRight, Star, ExternalLink } from 'lucide-react';

const Landing = () => {
  const features = [
    {
      icon: <MessageSquare className="w-6 h-6 md:w-8 md:h-8" />,
      title: "Простой конструктор триггеров",
      description: "Создавайте сложные сценарии без программирования"
    },
    {
      icon: <Zap className="w-6 h-6 md:w-8 md:h-8" />,
      title: "Отправка в обычные и топик-чаты",
      description: "Гибкая маршрутизация сообщений"
    },
    {
      icon: <BarChart3 className="w-6 h-6 md:w-8 md:h-8" />,
      title: "Полная статистика с графиками",
      description: "Аналитика в реальном времени"
    },
    {
      icon: <Send className="w-6 h-6 md:w-8 md:h-8" />,
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

  const reviews = [
    {
      author: "@Fopertion",
      role: "Владелец ИИ-бота (@Alia_Nova_Bot)",
      text: "Создание ИИ через DialogEngine — это по-настоящему имба. Платформа легко объясняет сложные вещи простым языком, у неё понятный интерфейс, а результат действительно работает так, как обещано. Это не просто игрушка — это реальный инструмент для создания рабочих ботов и умных диалоговых ИИ-систем.Почему это круто 1. Простота использованияВы не обязаны быть программистом, чтобы создать своего ИИ-ассистента.Платформа помогает шаг за шагом — от настройки диалогов до запуска. Всё логично, интуитивно и без зубрёжки документации.Интерфейс понятный даже новичкуНет необходимости писать сложный кодБыстрый старт и быстрый результатЭто огромный плюс для тех, кто впервые решил заняться ИИ. 2. Гибкая настройкаДаже если вы опытный разработчик, вы можете:детально настраивать поведение ИИсоздавать сложные сценарии разговораиспользовать условия, переменные и логикуподключать внешние данныеПлатформа позволяет выйти за рамки простого чат-бота и сделать полноценного интеллектуального ассистента. 3. ПроизводительностьБоты, созданные на DialogEngine, работают быстро и корректно.Ответы генерируются стабильно, задержек почти нет — это ощущается особенно, когда система обрабатывает много разнообразных запросов. 4. Поддержка и обучениеУ платформы есть: Чёткие инструкции Примеры Обучающие статьи Готовые шаблоны. Вы можете посмотреть, как устроены готовые ИИ-решения, и быстро адаптировать их под себя.Поддержка тоже отвечает оперативно — что немаловажно.",
      rating: 5
    },
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
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-green-900 to-gray-900 text-white">
      {/* Hero Section */}
      <div className="relative min-h-screen flex items-center justify-center px-4 sm:px-6 py-12">
        {/* Main Content */}
        <div className="relative z-10 max-w-6xl mx-auto text-center">
          {/* Logo */}
          <div className="mb-8 md:mb-12 inline-block">
            <div className="w-32 h-32 sm:w-48 sm:h-48 md:w-64 md:h-64 mx-auto bg-gradient-to-br from-green-400 to-green-600 rounded-2xl md:rounded-3xl shadow-2xl flex items-center justify-center">
              <div className="w-24 h-24 sm:w-36 sm:h-36 md:w-48 md:h-48 border-4 md:border-8 border-white/30 rounded-xl md:rounded-2xl flex items-center justify-center">
                <MessageSquare className="w-16 h-16 sm:w-24 sm:h-24 md:w-32 md:h-32 text-white" strokeWidth={1.5} />
              </div>
            </div>
          </div>

          {/* Headline */}
          <h1 className="text-3xl sm:text-4xl md:text-6xl lg:text-7xl font-black mb-4 md:mb-6 bg-clip-text text-transparent bg-gradient-to-r from-white via-green-200 to-white px-4">
            Dialoge Engine — корпоративные боты нового поколения
          </h1>

          <p className="text-base sm:text-lg md:text-xl lg:text-2xl text-gray-300 mb-8 md:mb-12 max-w-4xl mx-auto leading-relaxed px-4">
            Мощный конструктор для бизнеса: триггеры, Keyboard-кнопки, рассылки и аналитика в реальном времени.
          </p>

          {/* Feature Grid */}
          <div className="grid sm:grid-cols-2 gap-4 md:gap-6 mb-8 md:mb-12 max-w-4xl mx-auto px-4">
            {features.map((feature, i) => (
              <div 
                key={i}
                className="bg-black/40 backdrop-blur-lg border border-green-500/20 rounded-xl md:rounded-2xl p-4 md:p-6 text-left hover:border-green-500/40 transition-all duration-300"
              >
                <div className="text-green-400 mb-2 md:mb-3">{feature.icon}</div>
                <h3 className="font-bold text-base md:text-xl mb-1 md:mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-xs md:text-sm">{feature.description}</p>
              </div>
            ))}
          </div>

          {/* CTA Button */}
          <a 
            href="/auth"
            className="inline-flex items-center gap-2 md:gap-3 bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white font-black text-base md:text-lg px-8 md:px-12 py-4 md:py-5 rounded-full shadow-2xl transition-all duration-300 hover:scale-105"
          >
            Подключиться / Узнать больше
            <ArrowRight className="w-5 h-5 md:w-6 md:h-6" />
          </a>

          <p className="mt-4 md:mt-6 text-gray-500 text-xs md:text-sm px-4">
            Команда: <a href="https://t.me/Kotickr" target="_blank" rel="noopener noreferrer" className="text-green-400 hover:underline">@kotickr</a>, <a href="https://t.me/mrakotik" target="_blank" rel="noopener noreferrer" className="text-green-400 hover:underline">@mrakotik</a> + #HWM
          </p>
        </div>
      </div>

      {/* Partners Section */}
      <div className="py-12 md:py-20 px-4 sm:px-6 bg-black/30 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-black text-center mb-8 md:mb-12">Наши партнёры</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8 max-w-lg lg:max-w-none mx-auto">
            {partners.map((partner, i) => (
              <a
                key={i}
                href={partner.url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl md:rounded-2xl p-6 md:p-8 text-center hover:scale-105 transition-all duration-300 border border-green-500/20 hover:border-green-500/60 group"
              >
                <div className="w-20 h-20 md:w-24 md:h-24 mx-auto mb-4 md:mb-6 rounded-full bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center text-3xl md:text-4xl font-black text-white">
                  {partner.initial}
                </div>
                <h3 className="font-bold text-lg md:text-xl mb-2 group-hover:text-green-400 transition-colors">{partner.name}</h3>
                <p className="text-gray-400 text-sm mb-4">{partner.description}</p>
                <ExternalLink className="w-4 h-4 md:w-5 md:h-5 mx-auto text-green-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Reviews Section */}
      <div className="py-12 md:py-20 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-black text-center mb-8 md:mb-12">Отзывы клиентов</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
            {reviews.map((review, i) => (
              <div
                key={i}
                className="bg-black/40 backdrop-blur-lg border border-green-500/20 rounded-xl md:rounded-2xl p-5 md:p-6 hover:border-green-500/40 transition-all duration-300"
              >
                <div className="flex gap-1 mb-3 md:mb-4">
                  {[...Array(review.rating)].map((_, j) => (
                    <Star key={j} className="w-4 h-4 md:w-5 md:h-5 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-300 mb-4 md:mb-6 italic text-sm md:text-base">"{review.text}"</p>
                <div className="border-t border-gray-700 pt-3 md:pt-4">
                  <p className="font-bold text-sm md:text-base">{review.author}</p>
                  <p className="text-xs md:text-sm text-gray-500">{review.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Team Section */}
      <div className="py-12 md:py-20 px-4 sm:px-6 bg-black/30 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-black text-center mb-8 md:mb-12">Наша команда</h2>
          <div className="grid sm:grid-cols-2 gap-6 md:gap-8 max-w-lg md:max-w-none mx-auto">
            {team.map((member, i) => (
              <a
                key={i}
                href={member.telegram}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl md:rounded-2xl p-6 md:p-8 text-center hover:scale-105 transition-all duration-300 border border-green-500/20 hover:border-green-500/60 group"
              >
                <div className="w-16 h-16 md:w-20 md:h-20 mx-auto mb-3 md:mb-4 rounded-full bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center text-2xl md:text-4xl font-black text-white">
                  {member.name[0]}
                </div>
                <h3 className="font-bold text-lg md:text-xl mb-2 group-hover:text-green-400 transition-colors">{member.name}</h3>
                <p className="text-gray-400 text-sm mb-3 md:mb-4">{member.role}</p>
                <ExternalLink className="w-4 h-4 md:w-5 md:h-5 mx-auto text-green-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-8 md:py-12 px-4 sm:px-6 border-t border-gray-800">
        <div className="max-w-6xl mx-auto text-center">
          <p className="text-gray-500 text-sm md:text-base">
            © 2026 Dialoge Engine. Корпоративные боты нового поколения.
          </p>
          <p className="text-gray-600 text-xs md:text-sm mt-2">
            Создано с 💚
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Landing;

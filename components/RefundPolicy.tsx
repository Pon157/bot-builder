import React from 'react';
import { ShieldCheck, RefreshCcw, AlertTriangle } from 'lucide-react';

const RefundPolicy: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto p-6 md:p-12 text-zinc-300 bg-[#121212] border border-zinc-800 rounded-[2.5rem] my-10 shadow-2xl animate-in fade-in duration-500">
      <header className="mb-10 text-center">
        <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">Политика возврата и лицензирования</h1>
        <p className="text-sm text-zinc-500 uppercase tracking-[0.2em]">Последнее обновление: Февраль 2026</p>
      </header>

      <div className="space-y-8">
        {/* Секция 1: Цифровой контент */}
        <section className="bg-black/40 p-6 rounded-2xl border border-zinc-800">
          <h2 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <ShieldCheck className="w-5 h-5 text-blue-500" /> 1. Цифровой контент
          </h2>
          <div className="space-y-3 text-sm leading-relaxed">
            <p>1.1. Лицензионный ключ является цифровым товаром и активирует услуги мгновенно после его ввода в личном кабинете.</p>
            <p>1.2. В соответствии с законодательством РФ, цифровые товары надлежащего качества после активации доступа (предоставления права использования) возврату и обмену не подлежат.</p>
            <p>1.3. Покупка ключа является полностью добровольным решением пользователя. Платформа не навязывает услуги и предоставляет всю информацию о функционале до момента оплаты.</p>
          </div>
        </section>

        {/* Секция 2: Условия возврата */}
        <section className="bg-black/40 p-6 rounded-2xl border border-zinc-800">
          <h2 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <RefreshCcw className="w-5 h-5 text-emerald-500" /> 2. Условия возврата
          </h2>
          <div className="space-y-3 text-sm leading-relaxed">
            <p>2.1. Возврат средств возможен только в случае подтвержденных технических проблем на стороне Платформы, которые делают невозможным функционирование бота более чем на 24 часа.</p>
            <p>2.2. Для оформления возврата по техническим причинам пользователь должен обратиться в техподдержку с описанием проблемы.</p>
          </div>
        </section>

        {/* Секция 3: Тестовый период */}
        <section className="bg-black/40 p-6 rounded-2xl border border-zinc-800">
          <h2 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> 3. Тестовый период
          </h2>
          <div className="space-y-3 text-sm leading-relaxed">
            <p>3.1. Платформа предоставляет бесплатный период (триал) для ознакомления.</p>
            <p>3.2. Пользователь обязан использовать этот период для проверки совместимости своих задач с функциями Платформы до совершения покупки. Факт оплаты означает, что пользователь ознакомлен с функционалом и он его устраивает.</p>
          </div>
        </section>
      </div>

      <footer className="mt-12 pt-8 border-t border-zinc-800 text-center text-xs text-zinc-600">
        <p>Самозанятый Сазонов В.А | ИНН 503818798300</p>
        <p className="mt-2">По всем вопросам: vitechek.208@gmail.com</p>
      </footer>
    </div>
  );
};

export default RefundPolicy;

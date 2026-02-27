import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, ArrowRight } from 'lucide-react';

const SuccessPage: React.FC = () => {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center space-y-6 animate-in fade-in zoom-in duration-500">
      <div className="w-20 h-20 bg-emerald-500/20 rounded-full flex items-center justify-center mb-4">
        <CheckCircle className="w-12 h-12 text-emerald-500" />
      </div>
      
      <h1 className="text-3xl font-black text-white uppercase tracking-tighter">Оплата принята!</h1>
      
      <div className="max-w-md space-y-2">
        <p className="text-zinc-400 text-sm">
          Ваш платеж успешно обработан. Деньги будут начислены на Ваш аккаунт в течение 1-2 минут.
        </p>
      </div>

      <Link to="/profile" 
        className="flex items-center gap-2 px-8 py-4 bg-white text-black font-black rounded-xl hover:bg-zinc-200 transition-all uppercase tracking-widest text-xs">
        Вернуться в профиль <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
};

export default SuccessPage;

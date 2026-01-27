
import React from 'react';
import { User, SubscriptionPlan } from '../types';

interface ProfileProps {
  user: User;
  onUpdateUser: (user: User) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, onUpdateUser }) => {
  const plans: { type: SubscriptionPlan; price: string; bots: string; features: string[] }[] = [
    { type: 'FREE', price: '$0', bots: '1 Bot', features: ['Core Logic', 'Web Console', 'Basic Stats'] },
    { type: 'PRO', price: '$19/mo', bots: '10 Bots', features: ['All Core Features', 'Global Broadcast', 'Priority Support', 'Custom Keyboards'] },
    { type: 'ENTERPRISE', price: '$99/mo', bots: 'Unlimited', features: ['White Label', 'API Access', 'Custom Deployment', 'Dedicated Manager'] }
  ];

  const handleUpgrade = (plan: SubscriptionPlan) => {
    onUpdateUser({ ...user, subscription: plan });
    alert(`Success! You have switched to the ${plan} plan.`);
  };

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-bold mb-2">Account Management</h1>
        <p className="text-zinc-500">Overview of your subscription, billing status and infrastructure limits.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-8">
                <div className="flex items-center gap-6 mb-8">
                    <div className="w-20 h-20 bg-blue-600 rounded-2xl flex items-center justify-center text-3xl font-bold text-white shadow-xl shadow-blue-600/10">
                        {user.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold text-white">{user.username}</h2>
                        <p className="text-zinc-500 text-sm">{user.email}</p>
                        <div className="mt-2 flex gap-2">
                             <span className="text-[10px] font-black bg-blue-500/10 text-blue-500 border border-blue-500/20 px-2 py-0.5 rounded uppercase tracking-tighter">
                                {user.subscription} PLAN
                             </span>
                             <span className="text-[10px] font-black bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded uppercase tracking-tighter">
                                ID: {user.id}
                             </span>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                        <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1">Infrastructure</p>
                        <p className="text-2xl font-bold text-white">{user.botsCreated} <span className="text-sm font-normal text-zinc-500">Nodes</span></p>
                    </div>
                    <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                        <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1">Wallet Balance</p>
                        <p className="text-2xl font-bold text-green-500">${user.balance.toFixed(2)}</p>
                    </div>
                    <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                        <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1">Status</p>
                        <p className="text-2xl font-bold text-white">Verified</p>
                    </div>
                </div>
            </section>

            <section className="space-y-6">
                <h3 className="text-xl font-bold">Select Subscription</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {plans.map(plan => (
                        <div 
                            key={plan.type}
                            className={`bg-[#121212] border p-6 rounded-3xl transition-all ${user.subscription === plan.type ? 'border-blue-500 bg-blue-500/5' : 'border-zinc-800 hover:border-zinc-700'}`}
                        >
                            <div className="flex justify-between items-start mb-4">
                                <h4 className="text-sm font-bold uppercase tracking-widest">{plan.type}</h4>
                                {user.subscription === plan.type && <span className="text-[9px] bg-blue-500 text-white px-2 py-0.5 rounded-full font-bold">ACTIVE</span>}
                            </div>
                            <div className="mb-6">
                                <span className="text-3xl font-bold text-white">{plan.price}</span>
                                <span className="text-zinc-500 text-xs ml-1">/ mo</span>
                            </div>
                            <ul className="text-[11px] text-zinc-400 space-y-2 mb-8">
                                <li className="font-bold text-white">✓ {plan.bots}</li>
                                {plan.features.map(f => <li key={f}>✓ {f}</li>)}
                            </ul>
                            <button 
                                onClick={() => handleUpgrade(plan.type)}
                                disabled={user.subscription === plan.type}
                                className={`w-full py-3 rounded-xl text-xs font-bold transition-all ${user.subscription === plan.type ? 'bg-zinc-800 text-zinc-500' : 'bg-white text-black hover:bg-zinc-200'}`}
                            >
                                {user.subscription === plan.type ? 'Current Plan' : 'Select Plan'}
                            </button>
                        </div>
                    ))}
                </div>
            </section>
        </div>

        <div className="space-y-6">
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
                <h3 className="text-sm font-bold mb-4 uppercase tracking-widest text-zinc-500">Recent Invoices</h3>
                <div className="space-y-4">
                    <div className="flex items-center justify-between text-xs">
                        <div>
                            <p className="text-white font-medium">Internal Top-up</p>
                            <p className="text-zinc-600">January 27, 2026</p>
                        </div>
                        <span className="text-green-500 font-bold">+$50.00</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                        <div>
                            <p className="text-white font-medium">Free Plan Migration</p>
                            <p className="text-zinc-600">January 27, 2026</p>
                        </div>
                        <span className="text-zinc-500 font-bold">$0.00</span>
                    </div>
                </div>
            </div>
            
            <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-6">
                <h3 className="text-sm font-bold text-blue-400 mb-2">Professional Support</h3>
                <p className="text-xs text-blue-300 leading-relaxed opacity-70">
                    Need help with Ubuntu server setup or custom bot logic? Our team is available for enterprise integration.
                </p>
                <button className="mt-4 text-[10px] font-bold text-white uppercase tracking-widest bg-blue-600 px-4 py-2 rounded-lg">Open Ticket</button>
            </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;

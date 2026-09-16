/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/templates/**/*.html',
    './app/static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f8f5ff',
          100: '#f0eafe',
          200: '#e0d4fb',
          300: '#c6afea',
          400: '#a37ad3',
          500: '#8253ba',
          600: '#693b9b',
          700: '#552f80',
          800: '#422665',
          900: '#2e1c48',
          950: '#191026',
        },
      },
      boxShadow: {
        'cosmic-sm': '0 8px 24px rgba(46, 28, 72, 0.08)',
        cosmic: '0 20px 50px rgba(46, 28, 72, 0.13)',
      },
    },
  },
  safelist: [
    'bg-brand-50', 'bg-brand-100', 'bg-brand-600', 'bg-brand-700',
    'border-brand-200', 'border-brand-300', 'border-brand-600',
    'text-brand-600', 'text-brand-700', 'text-brand-800',
    'ring-brand-400', 'ring-brand-500', 'ring-2', 'ring',
    'opacity-50', 'opacity-70', 'cursor-not-allowed', 'hidden',
    'animate-spin', 'bg-green-50', 'bg-green-100', 'bg-green-600',
    'border-green-300', 'text-green-700', 'text-green-800',
    'bg-red-50', 'bg-red-100', 'border-red-300', 'text-red-700', 'text-red-800',
  ],
  plugins: [],
};

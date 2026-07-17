export function Header() {
  return (
    <header className="fixed top-0 right-0 h-[50px] frame-surface flex items-center justify-end px-4 md:px-6 z-10">
      <button
        type="button"
        className="w-8 h-8 rounded-full border border-white/30 flex items-center justify-center text-white hover:border-white/60 transition-colors"
        aria-label="Usuario"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </button>
    </header>
  )
}

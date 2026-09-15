/**
 * App header — reproduces the approved design's header exactly:
 * logo + brand, centered nav with an active "Automate" pill, and the
 * avatar on the right. Static: nothing here calls the backend.
 */

import './Header.css';

const AVATAR_INITIALS = 'AM';

export function Header() {
  return (
    <header className="amdr-header">
      <div className="amdr-header__inner">
        <div className="amdr-header__brand">
          <img src="/cdc-logo.png" alt="CDC logo" className="amdr-header__logo" />
          <div className="amdr-header__brand-text">
            <div className="amdr-header__product">Auto MDR</div>
            <div className="amdr-header__company">CDC International Private Limited</div>
          </div>
        </div>

        <nav className="amdr-header__nav">
          <span className="amdr-header__nav-item amdr-header__nav-item--active">Automate</span>
          <a href="#" className="amdr-header__nav-item">
            How it works
          </a>
          <a href="#" className="amdr-header__nav-item">
            Support
          </a>
        </nav>

        <div className="amdr-header__meta">
          <div className="amdr-header__avatar" aria-label="Signed in as AM" title="AM">
            {AVATAR_INITIALS}
          </div>
        </div>
      </div>
    </header>
  );
}

/**
 * App header — reproduces the approved design's header exactly:
 * logo + brand, centered nav with an active "Automate" pill, and the
 * plant/avatar block on the right.
 *
 * Static for now: there is one nav destination and one plant. Nothing here
 * calls the backend — see `services/mdrService.ts` in a later phase for the
 * real plant list.
 */

import './Header.css';

/** The plant every submission is uploaded against until there is a plant
 * selector. Matched by code against `GET /api/v1/plants` when uploading. */
export const PLANT_CODE = 'QATARENERGY-TN';
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
          <div className="amdr-header__plant">
            <div className="amdr-header__plant-label">PLANT</div>
            <div className="amdr-header__plant-value">{PLANT_CODE}</div>
          </div>
          <div className="amdr-header__avatar">{AVATAR_INITIALS}</div>
        </div>
      </div>
    </header>
  );
}

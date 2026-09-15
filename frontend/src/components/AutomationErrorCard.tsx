/**
 * Shown inside the workbook panel when a real upload/extract/automate request
 * fails. Same error visual language as `UploadErrorCard` (`UploadErrorCard.css`
 * is shared between the two) with copy for an actual backend failure and a
 * retry action, since the file is still held in memory — and still shown in
 * the workbook row above — so nothing has to be re-selected to try again.
 */

import { AlertTriangle } from 'lucide-react';

import './UploadErrorCard.css';

interface AutomationErrorCardProps {
  message: string;
  onRetry: () => void;
  onChangeWorkbook: () => void;
}

export function AutomationErrorCard({ message, onRetry, onChangeWorkbook }: AutomationErrorCardProps) {
  return (
    <div className="amdr-error amdr-error--inline" role="alert">
      <div className="amdr-error__status">
        <span className="amdr-error__icon">
          <AlertTriangle size={20} color="#B23B27" strokeWidth={2} />
        </span>
        <div>
          <h2 className="amdr-error__heading">Automation couldn&rsquo;t be completed</h2>
          <p className="amdr-error__subtext">The workbook is still here — you can try again or choose another.</p>
        </div>
      </div>
      <div className="amdr-error__message">
        <p>{message}</p>
      </div>
      <div className="amdr-error__actions">
        <button type="button" className="amdr-error__button" onClick={onRetry}>
          Try again
        </button>
        <button type="button" className="amdr-error__secondary-button" onClick={onChangeWorkbook}>
          Change workbook
        </button>
      </div>
    </div>
  );
}

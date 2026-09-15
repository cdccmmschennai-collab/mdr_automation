/**
 * The completion content — shown inside the workbook panel once
 * `POST .../automate` has actually succeeded.
 *
 * Every figure comes from the real `GET .../summary` response
 * (`SummaryResponse` in `backend/app/api/schemas/mdr.py`) — nothing here is
 * computed or invented. A summary fetch failure is shown inline with its own
 * retry and never implies the automation itself failed; same for a download
 * failure.
 */

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, Loader2 } from 'lucide-react';

import type { SummaryResponse } from '../types/api';
import { downloadWorkbook } from '../services/mdrService';
import './ResultCard.css';

interface ResultCardProps {
  fileName: string;
  mdrId: string;
  summary?: SummaryResponse;
  summaryError?: string;
  onRetrySummary: () => void;
  onReset: () => void;
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ResultCard({ fileName, mdrId, summary, summaryError, onRetrySummary, onReset }: ResultCardProps) {
  const [downloadState, setDownloadState] = useState<'idle' | 'downloading' | 'error'>('idle');
  const [downloadError, setDownloadError] = useState('');

  const handleDownload = async () => {
    if (downloadState === 'downloading') return;
    setDownloadState('downloading');
    setDownloadError('');
    try {
      const { blob, filename } = await downloadWorkbook(mdrId);
      triggerBrowserDownload(blob, filename ?? fileName);
      setDownloadState('idle');
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'The workbook could not be downloaded.';
      setDownloadError(message);
      setDownloadState('error');
    }
  };

  return (
    <div className="amdr-result">
      <div className="amdr-result__status">
        <CheckCircle2 size={22} color="#2EAD63" />
        <div>
          <h2 className="amdr-result__heading">Automation complete</h2>
          <p className="amdr-result__subtext">
            {summary?.rule_set
              ? `Automated with rule set ${summary.rule_set.version_label} · engine ${summary.engine_version}`
              : 'The automated workbook is ready to download.'}
          </p>
        </div>
      </div>

      {summary && (
        <dl className="amdr-result__strip">
          <div className="amdr-result__stat">
            <dd className="amdr-result__stat-value">{summary.row_count.toLocaleString()}</dd>
            <dt className="amdr-result__stat-label">Rows processed</dt>
          </div>
          <div className="amdr-result__stat">
            <dd className="amdr-result__stat-value">{summary.doc_type_populated.toLocaleString()}</dd>
            <dt className="amdr-result__stat-label">DOC TYPE populated</dt>
          </div>
          <div className="amdr-result__stat">
            <dd className="amdr-result__stat-value">{summary.idb_populated.toLocaleString()}</dd>
            <dt className="amdr-result__stat-label">IDB populated</dt>
          </div>
          <div className="amdr-result__stat">
            <dd className="amdr-result__stat-value amdr-result__stat-value--warning">
              {summary.idb_manual_check_required.toLocaleString()}
            </dd>
            <dt className="amdr-result__stat-label">Manual check required</dt>
          </div>
          <div className="amdr-result__stat">
            <dd className="amdr-result__stat-value amdr-result__stat-value--error">
              {summary.sow_unresolved.toLocaleString()}
            </dd>
            <dt className="amdr-result__stat-label">SOW unresolved</dt>
          </div>
        </dl>
      )}

      {summaryError && (
        <div className="amdr-result__summary-error" role="alert">
          <AlertTriangle size={15} color="#B23B27" />
          <p>{summaryError}</p>
          <button type="button" className="amdr-result__inline-retry" onClick={onRetrySummary}>
            Retry
          </button>
        </div>
      )}

      <div className="amdr-result__actions">
        <button
          type="button"
          className="amdr-result__download"
          onClick={() => void handleDownload()}
          disabled={downloadState === 'downloading'}
        >
          {downloadState === 'downloading' ? (
            <Loader2 size={17} color="#FFFFFF" className="spin-icon" />
          ) : (
            <Download size={17} color="#FFFFFF" />
          )}
          {downloadState === 'downloading' ? 'Downloading…' : 'Download Workbook'}
        </button>

        <button type="button" className="amdr-result__reset" onClick={onReset}>
          Automate another workbook
        </button>
      </div>

      {downloadState === 'error' && (
        <div className="amdr-result__download-error" role="alert">
          <AlertTriangle size={14} color="#B23B27" />
          <p>{downloadError}</p>
        </div>
      )}
    </div>
  );
}

/**
 * The upload card — the approved design's "ready" and "selected" states
 * (`isCardState` in Auto MDR.dc.html). The processing / complete / error
 * states live in separate cards: error today (`UploadErrorCard`), the rest
 * in Phase 3 once there is a real submission driving them.
 */

import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { ArrowRight, CheckCircle2, FileSpreadsheet, Lock, Upload, X } from 'lucide-react';

import { WorkbookIllustration } from './WorkbookIllustration';
import './UploadCard.css';

const PLANT_EYEBROW = 'QATARENERGY · WITHOUT DUMP';

export type UploadCardScreen = { kind: 'ready' } | { kind: 'selected'; file: File };

interface UploadCardProps {
  screen: UploadCardScreen;
  onFileSelected: (file: File) => void;
  onReset: () => void;
  onRunAutomation: () => void;
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '';
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function describeWorkbook(file: File): string {
  const isXlsm = file.name.toLowerCase().endsWith('.xlsm');
  const typeLabel = isXlsm ? 'Excel macro-enabled workbook (.xlsm)' : 'Excel workbook (.xlsx)';
  const sizeLabel = formatFileSize(file.size);
  return sizeLabel ? `${typeLabel} · ${sizeLabel}` : typeLabel;
}

export function UploadCard({ screen, onFileSelected, onReset, onRunAutomation }: UploadCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const openFilePicker = () => fileInputRef.current?.click();

  const handleCardClick = () => {
    if (screen.kind === 'ready') openFilePicker();
  };

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) onFileSelected(file);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onFileSelected(file);
  };

  return (
    <div
      className="amdr-upload-card"
      onClick={handleCardClick}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (screen.kind === 'ready' && (event.key === 'Enter' || event.key === ' ')) openFilePicker();
      }}
    >
      <div className="amdr-upload-card__row">
        {screen.kind === 'ready' ? (
          <div
            className={
              isDragging ? 'amdr-upload-card__content amdr-upload-card__content--dragging' : 'amdr-upload-card__content'
            }
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="amdr-upload-card__eyebrow">{PLANT_EYEBROW}</div>
            <h1 className="amdr-upload-card__heading">Automate MDR Workbook</h1>
            <p className="amdr-upload-card__lede">
              Upload your MDR workbook and Auto MDR will extract, validate and automate the data for you.
            </p>

            <button
              type="button"
              className="amdr-upload-card__button"
              onClick={(event) => {
                event.stopPropagation();
                openFilePicker();
              }}
            >
              <Upload size={16} color="#FFFFFF" />
              Upload workbook
            </button>

            <div className="amdr-upload-card__hint">
              {isDragging ? 'Drop workbook to upload' : 'or drag and drop your file here'}
            </div>
            <div className="amdr-upload-card__formats">
              Supported formats: <span className="amdr-upload-card__format">.xlsx</span> and{' '}
              <span className="amdr-upload-card__format">.xlsm</span>
            </div>
          </div>
        ) : (
          <div className="amdr-upload-card__selected">
            <div className="amdr-upload-card__eyebrow">{PLANT_EYEBROW}</div>
            <h1 className="amdr-upload-card__heading amdr-upload-card__heading--selected">Start with your workbook</h1>

            <div className="amdr-upload-card__file-row">
              <FileSpreadsheet size={22} color="#1B5F95" className="amdr-upload-card__file-icon" />
              <div className="amdr-upload-card__file-info">
                <div className="amdr-upload-card__file-name">{screen.file.name}</div>
                <div className="amdr-upload-card__file-meta">{describeWorkbook(screen.file)}</div>
              </div>
              <CheckCircle2 size={19} color="#2EAD63" className="amdr-upload-card__file-check" />
            </div>

            <div className="amdr-upload-card__actions">
              <button
                type="button"
                className="amdr-upload-card__button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRunAutomation();
                }}
              >
                Run Automation
                <ArrowRight size={15} color="#FFFFFF" />
              </button>
              <button
                type="button"
                className="amdr-upload-card__secondary-button"
                onClick={(event) => {
                  event.stopPropagation();
                  onReset();
                }}
              >
                <X size={14} />
                Change workbook
              </button>
            </div>

            <div className="amdr-upload-card__security-note">
              <Lock size={13} color="#6F7880" />
              <p>Processed securely and used only to generate the automated workbook.</p>
            </div>
          </div>
        )}

        {screen.kind === 'ready' && (
          <div className="amdr-upload-card__illustration">
            <WorkbookIllustration />
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xlsm"
        className="amdr-upload-card__file-input"
        onClick={(event) => event.stopPropagation()}
        onChange={handleFileInputChange}
      />
    </div>
  );
}

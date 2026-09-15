/**
 * The workspace's "ready" content — the approved design's upload state
 * (`isCardState` in Auto MDR.dc.html) — rendered inside the shared
 * `.amdr-workspace` frame on the Automate page. It fills the frame so the
 * whole banner remains the click and drop target, exactly as before.
 *
 * Once a workbook is chosen the page swaps this for `WorkbookPanel` inside
 * the same frame, so the workspace reads as one surface whose content has
 * moved on.
 */

import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { Upload } from 'lucide-react';

import { WorkbookIllustration } from './WorkbookIllustration';
import { MODE_EYEBROW } from './modeLabels';
import './UploadCard.css';

interface UploadCardProps {
  onFileSelected: (file: File) => void;
}

export function UploadCard({ onFileSelected }: UploadCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const openFilePicker = () => fileInputRef.current?.click();

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
      className={isDragging ? 'amdr-upload-card amdr-upload-card--dragging' : 'amdr-upload-card'}
      onClick={openFilePicker}
      role="button"
      tabIndex={0}
      aria-label="Upload an MDR workbook (.xlsx or .xlsm)"
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openFilePicker();
        }
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="amdr-upload-card__row">
        <div className="amdr-upload-card__content">
          <div className="amdr-upload-card__eyebrow">{MODE_EYEBROW}</div>
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

          <div className="amdr-upload-card__hint" aria-live="polite">
            {isDragging ? 'Drop workbook to upload' : 'or drag and drop your file here'}
          </div>
          <div className="amdr-upload-card__formats">
            Supported formats: <span className="amdr-upload-card__format">.xlsx</span> and{' '}
            <span className="amdr-upload-card__format">.xlsm</span>
          </div>
        </div>

        <div className="amdr-upload-card__illustration">
          <WorkbookIllustration />
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xlsm"
        className="amdr-upload-card__file-input"
        aria-hidden="true"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        onChange={handleFileInputChange}
      />
    </div>
  );
}

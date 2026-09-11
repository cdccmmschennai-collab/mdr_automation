/**
 * The Auto MDR workflow page.
 *
 * Owns the upload/processing state machine: ready, selected, invalid file,
 * processing (upload → extract → automate), complete and failed. Each
 * processing transition is driven by the real request's outcome — nothing
 * here fakes progress or invents a backend step. The summary fetch that
 * feeds the complete screen runs exactly once, right after automate
 * succeeds — never on a render or a poll — and its failure never demotes a
 * successful automation back to the failed screen.
 */

import { useCallback, useEffect, useState } from 'react';

import { AutomationErrorCard } from '../components/AutomationErrorCard';
import { Header, PLANT_CODE } from '../components/Header';
import { ProcessingCard, type ProcessingStage } from '../components/ProcessingCard';
import { ResultCard } from '../components/ResultCard';
import { UploadCard, type UploadCardScreen } from '../components/UploadCard';
import { UploadErrorCard } from '../components/UploadErrorCard';
import { automateSubmission, extractSubmission, getSummary, uploadWorkbook } from '../services/mdrService';
import { listPlants } from '../services/plantService';
import type { SummaryResponse } from '../types/api';
import './AutomatePage.css';

const SUPPORTED_EXTENSIONS = ['.xlsx', '.xlsm'];

type UploadScreen =
  | UploadCardScreen
  | { kind: 'invalid'; fileName: string; message: string }
  | { kind: 'processing'; file: File; stage: ProcessingStage; done: boolean; mdrId?: string }
  | { kind: 'complete'; file: File; mdrId: string; summary?: SummaryResponse; summaryError?: string }
  | { kind: 'failed'; file: File; message: string };

function summaryErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : 'The result summary could not be loaded.';
}

function isSupportedWorkbook(file: File): boolean {
  const name = file.name.toLowerCase();
  return SUPPORTED_EXTENSIONS.some((extension) => name.endsWith(extension));
}

export function AutomatePage() {
  const [screen, setScreen] = useState<UploadScreen>({ kind: 'ready' });

  const handleFileSelected = useCallback((file: File) => {
    if (!isSupportedWorkbook(file)) {
      setScreen({ kind: 'invalid', fileName: file.name, message: 'Please upload an .xlsx or .xlsm workbook.' });
      return;
    }
    setScreen({ kind: 'selected', file });
  }, []);

  const handleChangeWorkbook = useCallback(() => setScreen({ kind: 'ready' }), []);

  const runAutomation = useCallback(async (file: File) => {
    setScreen({ kind: 'processing', file, stage: 'uploading', done: false });
    try {
      const plants = await listPlants();
      const target = PLANT_CODE.toLowerCase();
      const plant = plants.find(
        (candidate) => candidate.code.toLowerCase() === target || candidate.name.toLowerCase() === target,
      );
      if (!plant) {
        throw new Error(`No plant is registered for ${PLANT_CODE}. Contact an administrator to register it.`);
      }

      const uploaded = await uploadWorkbook(plant.id, file);
      setScreen({ kind: 'processing', file, stage: 'extracting', done: false, mdrId: uploaded.mdr_id });

      await extractSubmission(uploaded.mdr_id);
      setScreen({ kind: 'processing', file, stage: 'automating', done: false, mdrId: uploaded.mdr_id });

      await automateSubmission(uploaded.mdr_id);
      setScreen({ kind: 'processing', file, stage: 'automating', done: true, mdrId: uploaded.mdr_id });

      // Automation has already succeeded at this point. A summary failure is
      // reported on the complete screen, not as an automation failure.
      try {
        const summary = await getSummary(uploaded.mdr_id);
        setScreen({ kind: 'complete', file, mdrId: uploaded.mdr_id, summary });
      } catch (cause) {
        setScreen({ kind: 'complete', file, mdrId: uploaded.mdr_id, summaryError: summaryErrorMessage(cause) });
      }
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : 'The workbook could not be processed. Check the file and try again.';
      setScreen({ kind: 'failed', file, message });
    }
  }, []);

  const handleRunAutomation = useCallback(() => {
    if (screen.kind === 'selected') void runAutomation(screen.file);
  }, [screen, runAutomation]);

  const handleRetry = useCallback(() => {
    if (screen.kind === 'failed') void runAutomation(screen.file);
  }, [screen, runAutomation]);

  const handleRetrySummary = useCallback(() => {
    if (screen.kind !== 'complete') return;
    const { file, mdrId } = screen;
    void getSummary(mdrId)
      .then((summary) => setScreen({ kind: 'complete', file, mdrId, summary }))
      .catch((cause) => setScreen({ kind: 'complete', file, mdrId, summaryError: summaryErrorMessage(cause) }));
  }, [screen]);

  // Dropping a file anywhere outside the upload card must not navigate the
  // browser away to display it.
  useEffect(() => {
    const preventNavigation = (event: globalThis.DragEvent) => event.preventDefault();
    window.addEventListener('dragover', preventNavigation);
    window.addEventListener('drop', preventNavigation);
    return () => {
      window.removeEventListener('dragover', preventNavigation);
      window.removeEventListener('drop', preventNavigation);
    };
  }, []);

  return (
    <div className="amdr-page">
      <Header />
      <div className="amdr-page__hero">
        <div className="amdr-page__hero-inner">
          {screen.kind === 'invalid' && (
            <UploadErrorCard fileName={screen.fileName} message={screen.message} onChooseAnother={handleChangeWorkbook} />
          )}
          {screen.kind === 'processing' && (
            <ProcessingCard fileName={screen.file.name} stage={screen.stage} done={screen.done} />
          )}
          {screen.kind === 'failed' && (
            <AutomationErrorCard
              fileName={screen.file.name}
              message={screen.message}
              onRetry={handleRetry}
              onChangeWorkbook={handleChangeWorkbook}
            />
          )}
          {screen.kind === 'complete' && (
            <ResultCard
              fileName={screen.file.name}
              mdrId={screen.mdrId}
              summary={screen.summary}
              summaryError={screen.summaryError}
              onRetrySummary={handleRetrySummary}
              onReset={handleChangeWorkbook}
            />
          )}
          {(screen.kind === 'ready' || screen.kind === 'selected') && (
            <UploadCard
              screen={screen}
              onFileSelected={handleFileSelected}
              onReset={handleChangeWorkbook}
              onRunAutomation={handleRunAutomation}
            />
          )}
        </div>
      </div>
    </div>
  );
}

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
 *
 * Every state renders inside one `.amdr-workspace` frame: the upload content
 * before a workbook is chosen, the `WorkbookPanel` from then on. The plant
 * the submission belongs to is the first one `GET /api/v1/plants` returns
 * (there is one registered plant; a selector can be added when there are
 * more) — nothing about it is hard-coded on the client.
 */

import { useCallback, useEffect, useState } from 'react';

import { Header } from '../components/Header';
import { type ProcessingStage } from '../components/ProcessRail';
import { UploadCard } from '../components/UploadCard';
import { UploadErrorCard } from '../components/UploadErrorCard';
import { WorkbookPanel, type WorkbookPanelState } from '../components/WorkbookPanel';
import { automateSubmission, extractSubmission, getSummary, uploadWorkbook } from '../services/mdrService';
import { listPlants } from '../services/plantService';
import type { PlantResponse, SummaryResponse } from '../types/api';
import './AutomatePage.css';

const SUPPORTED_EXTENSIONS = ['.xlsx', '.xlsm'];

type UploadScreen =
  | { kind: 'ready' }
  | { kind: 'selected'; file: File }
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

/** The workbook panel's file and state for every screen that has a chosen
 * workbook; null for the ready and invalid screens, which have none. */
function workbookPanelFor(screen: UploadScreen): { file: File; state: WorkbookPanelState } | null {
  switch (screen.kind) {
    case 'selected':
      return { file: screen.file, state: { kind: 'selected' } };
    case 'processing':
      return { file: screen.file, state: { kind: 'processing', stage: screen.stage, done: screen.done } };
    case 'complete':
      return {
        file: screen.file,
        state: { kind: 'complete', mdrId: screen.mdrId, summary: screen.summary, summaryError: screen.summaryError },
      };
    case 'failed':
      return { file: screen.file, state: { kind: 'failed', message: screen.message } };
    default:
      return null;
  }
}

export function AutomatePage() {
  const [screen, setScreen] = useState<UploadScreen>({ kind: 'ready' });

  // The registered plant list, loaded once. `null` until it has loaded;
  // an empty list means nothing is registered.
  const [plants, setPlants] = useState<PlantResponse[] | null>(null);
  const [plantsError, setPlantsError] = useState('');

  useEffect(() => {
    let cancelled = false;
    void listPlants()
      .then((list) => {
        if (!cancelled) setPlants(list);
      })
      .catch((cause) => {
        if (!cancelled) setPlantsError(cause instanceof Error ? cause.message : 'The plant list could not be loaded.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedPlant = plants?.[0];

  const handleFileSelected = useCallback((file: File) => {
    if (!isSupportedWorkbook(file)) {
      setScreen({ kind: 'invalid', fileName: file.name, message: 'Please upload an .xlsx or .xlsm workbook.' });
      return;
    }
    setScreen({ kind: 'selected', file });
  }, []);

  const handleChangeWorkbook = useCallback(() => setScreen({ kind: 'ready' }), []);

  const runAutomation = useCallback(async (file: File, plant: PlantResponse | undefined) => {
    setScreen({ kind: 'processing', file, stage: 'uploading', done: false });
    try {
      if (!plant) {
        throw new Error('No plant is registered. Contact an administrator to register one.');
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
    if (screen.kind === 'selected') void runAutomation(screen.file, selectedPlant);
  }, [screen, selectedPlant, runAutomation]);

  const handleRetry = useCallback(() => {
    if (screen.kind === 'failed') void runAutomation(screen.file, selectedPlant);
  }, [screen, selectedPlant, runAutomation]);

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

  const runBlockedReason = selectedPlant
    ? undefined
    : plantsError
      ? 'Run Automation needs a plant — the plant list could not be loaded.'
      : plants
        ? 'Run Automation needs a plant — none is registered yet.'
        : 'Run Automation needs a plant — loading the plant list.';

  const workspaceClassName = screen.kind === 'ready' ? 'amdr-workspace amdr-workspace--dropzone' : 'amdr-workspace';
  const panel = workbookPanelFor(screen);

  return (
    <div className="amdr-page">
      <Header />
      <div className="amdr-page__hero">
        <div className="amdr-page__hero-inner">
          <section className={workspaceClassName} aria-label="Workbook workspace">
            {screen.kind === 'ready' && <UploadCard onFileSelected={handleFileSelected} />}

            {screen.kind === 'invalid' && (
              <UploadErrorCard
                fileName={screen.fileName}
                message={screen.message}
                onChooseAnother={handleChangeWorkbook}
              />
            )}

            {panel && (
              <WorkbookPanel
                file={panel.file}
                state={panel.state}
                runBlockedReason={runBlockedReason}
                onRunAutomation={handleRunAutomation}
                onChangeWorkbook={handleChangeWorkbook}
                onRetry={handleRetry}
                onRetrySummary={handleRetrySummary}
              />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

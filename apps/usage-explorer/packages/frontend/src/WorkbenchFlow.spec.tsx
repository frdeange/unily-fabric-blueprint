import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

const backend = vi.hoisted(() => ({
  diagnoses: [] as DiagnosisRecord[],
  actions: [] as FollowUpRecord[],
  failLive: false,
}));

vi.mock('@microsoft/fabric-visuals', () => ({
  useCssTheme: () => ({}),
  VegaVisual: () => <div>Monthly chart</div>,
}));

vi.mock('@/hooks/use-adoption', () => ({
  useAdoption: () =>
    backend.failLive
      ? { status: 'error', message: 'Model access denied.', refresh: vi.fn() }
      : {
          status: 'ready',
          totals: [
            {
              tenant: 'tenant_example',
              period: '2026-08',
              events: 100,
              activeUsers: 5,
              avgDuration: 20,
            },
            {
              tenant: 'tenant_example',
              period: '2026-09',
              events: 120,
              activeUsers: 5,
              avgDuration: 30,
            },
          ],
          features: [
            {
              tenant: 'tenant_example',
              period: '2026-09',
              feature: 'Search',
              category: 'Discovery',
              events: 30,
              activeUsers: 4,
              avgDuration: 25,
            },
          ],
          refresh: vi.fn(),
        },
}));
vi.mock('@/lib/workbench-repository', () => ({
  loadWorkbench: async () => ({
    diagnoses: [...backend.diagnoses],
    actions: [...backend.actions],
  }),
  createDiagnosis: async (input: Omit<DiagnosisRecord, 'id' | 'owner_id'>) => {
    const record = { ...input, id: 'diagnosis-test', owner_id: 'owner-test' };
    backend.diagnoses.push(record);
    return record;
  },
  createFollowUp: async (
    input: Pick<
      FollowUpRecord,
      'diagnosis_id' | 'title' | 'notes' | 'priority' | 'dueDate'
    >,
  ) => {
    const record: FollowUpRecord = {
      ...input,
      id: 'action-test',
      owner_id: 'owner-test',
      status: 'Planned',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    backend.actions.push(record);
    return record;
  },
  updateFollowUp: async (id: string, patch: Partial<FollowUpRecord>) => {
    const index = backend.actions.findIndex((record) => record.id === id);
    backend.actions[index] = { ...backend.actions[index], ...patch };
    return backend.actions[index];
  },
  updateDiagnosis: vi.fn(),
}));

import { AdoptionWorkbench } from './AdoptionWorkbench';

describe('investigation to follow-through (offline contract tests)', () => {
  beforeEach(() => {
    backend.diagnoses = [];
    backend.actions = [];
    backend.failLive = false;
  });

  it('captures focused evidence, creates an action, edits status and reloads saved records', async () => {
    const app = render(<AdoptionWorkbench />);
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Capture a diagnosis' }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Capture a diagnosis' }),
    );
    fireEvent.change(screen.getByLabelText('Diagnosis title'), {
      target: { value: 'Validate search adoption' },
    });
    fireEvent.change(screen.getByLabelText('Your interpretation'), {
      target: {
        value: 'Validate the observation before proposing an intervention.',
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save diagnosis' }));
    await screen.findByText(/Diagnosis saved with its evidence snapshot/);
    expect(backend.diagnoses[0]).toMatchObject({
      feature: 'Search',
      events: 30,
      activeUsers: 4,
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Add follow-up action' }),
    );
    fireEvent.change(screen.getByLabelText('Action title'), {
      target: { value: 'Review the hypothesis' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create action' }));
    await screen.findByText(/Action saved. Its owner is you/);
    fireEvent.click(
      screen.getByRole('button', { name: 'Edit Review the hypothesis' }),
    );
    fireEvent.change(screen.getByLabelText('Status'), {
      target: { value: 'Done' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save action' }));
    await waitFor(() => expect(backend.actions[0].status).toBe('Done'));
    app.unmount();
    render(<AdoptionWorkbench />);
    await waitFor(() =>
      expect(screen.getByText('1 saved diagnoses')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Action board' }));
    expect(
      screen.getByRole('region', { name: 'Done actions' }),
    ).toHaveTextContent('Review the hypothesis');
  });

  it('keeps evidence accessible when live analytics fail', async () => {
    backend.diagnoses = [
      {
        id: 'diagnosis-test',
        owner_id: 'owner-test',
        title: 'Saved review',
        notes: 'User interpretation',
        tenant: 'tenant_example',
        period: '2026-09',
        feature: '',
        events: 120,
        activeUsers: 5,
        capturedAt: new Date(),
      },
    ];
    backend.failLive = true;
    render(<AdoptionWorkbench />);
    await waitFor(() =>
      expect(screen.getByText('1 saved diagnoses')).toBeInTheDocument(),
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Live analytics are unavailable',
    );
    fireEvent.click(screen.getByRole('button', { name: 'My diagnoses' }));
    expect(
      screen.getByRole('heading', { name: 'Saved review', level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByText('User interpretation')).toBeInTheDocument();
  });
});

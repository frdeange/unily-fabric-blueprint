//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  records: { diagnoses: [], actions: [] },
  createDiagnosis: vi.fn(),
  createFollowUp: vi.fn(),
}));

// Keep the smoke test offline: the real hook would call the live model.
vi.mock('@/hooks/use-semantic-model-query', () => ({
  useSemanticModelQuery: () => ({
    data: undefined,
    isLoading: true,
    error: undefined,
    refetch: async () => {},
  }),
}));

vi.mock('@/lib/workbench-repository', () => ({
  loadWorkbench: async () => mocks.records,
  createDiagnosis: mocks.createDiagnosis,
  createFollowUp: mocks.createFollowUp,
  updateDiagnosis: vi.fn(),
  updateFollowUp: vi.fn(),
}));

vi.mock('@microsoft/fabric-visuals', () => ({
  useCssTheme: () => ({}),
  VegaVisual: () => <div>Monthly chart</div>,
}));

import App from '@/App';

describe('App', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the workbench shell and a loading state while queries run', async () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { name: 'Adoption Workbench' }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(screen.getByText('0 saved diagnoses')).toBeInTheDocument(),
    );
  });

  it('keeps saved-record navigation usable while live analytics are loading', async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText('0 saved diagnoses')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'My diagnoses' }));
    expect(
      screen.getByText('Start with an observation, not an empty task'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Action board' }));
    expect(screen.getByText('Your action board is ready')).toBeInTheDocument();
  });
});

//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Keep the smoke test offline: the real hook would call the live model.
vi.mock('@/hooks/use-semantic-model-query', () => ({
  useSemanticModelQuery: () => ({
    data: undefined,
    isLoading: true,
    error: undefined,
    refetch: async () => {},
  }),
}));

import App from '@/App';

describe('App', () => {
  it('renders without throwing', () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it('shows the title and a loading state while queries run', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { name: 'Tenant Product Usage Explorer' })
    ).toBeInTheDocument();
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
  });
});

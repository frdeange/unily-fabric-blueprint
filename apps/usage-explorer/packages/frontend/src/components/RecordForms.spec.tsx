import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DiagnosisForm } from './RecordForms';

const evidence = {
  tenant: 'tenant_example',
  period: '2026-09',
  events: 120,
  activeUsers: 5,
  avgDuration: 30,
};

describe('evidence capture', () => {
  it('keeps the draft after a rejected save and allows retry', async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(new Error('Forbidden'))
      .mockResolvedValueOnce(undefined);
    render(<DiagnosisForm evidence={evidence} save={save} close={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Diagnosis title'), {
      target: { value: 'Investigate a hypothesis' },
    });
    fireEvent.change(screen.getByLabelText('Your interpretation'), {
      target: { value: 'Ask the customer to validate the observation.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save diagnosis' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Save failed');
    expect(screen.getByLabelText('Diagnosis title')).toHaveValue(
      'Investigate a hypothesis',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save diagnosis' }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenLastCalledWith(
      expect.objectContaining({
        tenant: 'tenant_example',
        events: 120,
        activeUsers: 5,
        previousEvents: null,
        title: 'Investigate a hypothesis',
      }),
    );
  });
});

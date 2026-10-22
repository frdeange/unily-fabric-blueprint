import { useCallback, useEffect, useRef, useState } from 'react';
import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

import { loadWorkbench } from '@/lib/workbench-repository';

export function useWorkbench() {
  const [data, setData] = useState<{
    diagnoses: DiagnosisRecord[];
    actions: FollowUpRecord[];
  }>({
    diagnoses: [],
    actions: [],
  });
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState('');
  const request = useRef(0);
  const load = useCallback(() => {
    const id = ++request.current;
    return loadWorkbench().then(
      (result) => {
        if (request.current !== id) return;
        setData(result);
        setStatus('ready');
      },
      () => {
        if (request.current !== id) return;
        setStatus('error');
        setError(
          'Saved records are unavailable. Verify that the workbench data service has been deployed and that you are signed in, then retry.',
        );
      },
    );
  }, []);
  const refresh = useCallback(async () => {
    setStatus('loading');
    setError('');
    await load();
  }, [load]);
  useEffect(() => {
    void load();
    return () => {
      request.current += 1;
    };
  }, [load]);

  return {
    ...data,
    status,
    error,
    refresh,
    storeDiagnosis: (record: DiagnosisRecord) =>
      setData((current) => ({
        ...current,
        diagnoses: [
          record,
          ...current.diagnoses.filter((item) => item.id !== record.id),
        ],
      })),
    storeAction: (record: FollowUpRecord) =>
      setData((current) => ({
        ...current,
        actions: [
          record,
          ...current.actions.filter((item) => item.id !== record.id),
        ],
      })),
  };
}
